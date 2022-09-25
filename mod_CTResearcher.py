#region Imports

import BigWorld
from CurrentVehicle import g_currentVehicle
from CurrentVehicle import g_currentPreviewVehicle
from gui.Scaleform.daapi.view.lobby.techtree import dumpers
from gui.Scaleform.daapi.view.lobby.techtree.settings import NODE_STATE
from gui.Scaleform.daapi.view.lobby.techtree.data import ResearchItemsData
from gui.Scaleform.daapi.view.lobby.techtree.settings import UnlockProps
from gui.Scaleform.daapi.view.lobby.techtree.techtree_dp import g_techTreeDP
from gui.Scaleform.daapi.view.lobby.techtree import unlock
from debug_utils import LOG_NOTE
from gui.shared.utils import decorators
from gui.shared.gui_items.items_actions import factory as ItemsActionsFactory
from gui import SystemMessages
from gui.Scaleform.framework.managers.containers import POP_UP_CRITERIA
from gui.Scaleform.genConsts.PREBATTLE_ALIASES import PREBATTLE_ALIASES
from frameworks.wulf import WindowLayer
from gui.app_loader.decorators import def_lobby
from gui.shared.gui_items.Vehicle import Vehicle
from items import vehicles
from gui.Scaleform.daapi.view.lobby.techtree.research_page import Research
from gui.Scaleform.genConsts.NODE_STATE_FLAGS import NODE_STATE_FLAGS
from gui.Scaleform.daapi.view.lobby.techtree.settings import NODE_STATE
from skeletons.gui.game_control import IPlatoonController
from gui.game_control.platoon_controller import _EPlatoonLayout
from skeletons.gui.impl import IGuiLoader
from helpers import dependency

import unicodedata
import imp
import time

#endregion

#region Vehicle researching

def getItem(itemCD):
	return g_currentVehicle.itemsCache.items.getItemByCD(itemCD)
	
def unlockItem(parentID, idx):
	if g_currentVehicle.itemsCache.items.stats.actualFreeXP < 3000000:
		pushErrorMessage("Unlocking is only available for CT. This message appeared because you have less than 3 000 000 Free XP.")
		return
	doUnlockItem(parentID, idx)

@decorators.adisp_process('research')
def doUnlockItem(parentID, unlockIdx):
	yield unlock.UnlockItemProcessor(parentID, unlockIdx, plugins=[]).request()

def researchVehicle(intCD, successorCD=0, callback=lambda: None):
	vehItem = getItem(intCD)
	unlockingSequence = []
	if not vehItem.isUnlocked:
		unlockTuple = g_techTreeDP.getUnlockProps(intCD)
		unlockingSequence.extend(researchVehicle(unlockTuple[0], intCD))
		MYLOG("Research {} ({}) for {} XP".format(vehItem.shortUserName, str(intCD), unlockTuple[2]))
	else:
		MYLOG("{} is already researched".format(vehItem.shortUserName))

	researchRequirementsArr = [data for data in vehItem.getUnlocksDescrs()]
	researchRequirements = {}
	for data in researchRequirementsArr:
		researchRequirements[data[2]] = data[3]

	if successorCD != 0:
		for unlockIdx, _, nodeCD, required in researchRequirementsArr:
			if nodeCD == successorCD:
				researched = set(vehItem.getAutoUnlockedItems())
				while len(required) > 0:
					requiredCopy = set(required)
					for itemCD in required:
						item = getItem(itemCD)
						if item.isUnlocked or itemCD in researched:
							requiredCopy.remove(itemCD)
							researched.add(itemCD)
							continue

						requiredForItem = researchRequirements[itemCD]
						if requiredForItem.issubset(researched):
							MYLOG(" - research {}".format(item.shortUserName))
							itemData = [data for data in researchRequirementsArr if data[2]==itemCD][0]
							unlockingSequence.append([intCD, itemData[0]])
							requiredCopy.remove(itemCD)
							researched.add(itemCD)
					required = requiredCopy
				
				itemData = [data for data in researchRequirementsArr if data[2]==successorCD][0]
				unlockingSequence.append([intCD, itemData[0]])
	else:
		researched = set(vehItem.getAutoUnlockedItems())
		itemsToBeResearched = len(researchRequirementsArr) + len(researched)

		for unlockIdx, xpCost, nodeCD, required in researchRequirementsArr:
			item = getItem(nodeCD)
			if item.isUnlocked:
				researched.add(nodeCD)

		itemsToBeResearched -= len(researched)

		while itemsToBeResearched > 0:
			for unlockIdx, xpCost, nodeCD, required in researchRequirementsArr:
				if required.issubset(researched):
					item = getItem(nodeCD)
					MYLOG(" - research {}".format(item.shortUserName))
					arr = [intCD, unlockIdx]
					if not nodeCD in researched:
						unlockingSequence.append(arr)
						researched.add(nodeCD)
						itemsToBeResearched -= 1

		MYLOG(unlockingSequence)
		combinedCallback = lambda: (pushInfoMessage("Fully unlocked {}".format(vehItem.shortUserName)), callback())	
		processQueue(unlockingSequence, lambda (parent, id): unlockItem(parent, id), 1, combinedCallback)

	return unlockingSequence

#endregion

#region Modules

def mountTopModules(vehCD):
	MYLOG("Mounting top modules")
	vehItem = getItem(vehCD)
	modules = [data for data in vehItem.getUnlocksDescrs()]
	bestModules = {}
	order = ['vehicleChassis', 'vehicleTurret', 'vehicleEngine', 'vehicleGun', 'vehicleRadio']
	for module in modules:
		item = getItem(module[2])
		if (isinstance(item, Vehicle)):
			continue
		moduleType = item.itemTypeName
		requiredModules = len(module[3])
		if not moduleType in bestModules:
			bestModules[moduleType] = module
		elif len(bestModules[moduleType][3]) < requiredModules or (len(bestModules[moduleType][3]) == requiredModules and bestModules[moduleType][1] < module[1]):
			bestModules[moduleType] = module

	MYLOG(str(bestModules))

	moduleCDs = []
	for moduleType in order:
		if moduleType in bestModules:
			moduleCDs.append(bestModules[moduleType][2])

	processQueue(moduleCDs, lambda module: buyAndMountModule(vehCD, module), 1, lambda: pushInfoMessage("Mounted top modules on {}".format(vehItem.shortUserName)))

def buyAndMountModule(vehCD, moduleCD):
	ItemsActionsFactory.doAction(ItemsActionsFactory.BUY_AND_INSTALL_AND_SELL_ITEM, moduleCD, vehCD, skipConfirm=True)

#endregion

#region Crew

def addCrewSkill(crewInvID, skillName, skillCount):
	xpCoef = 42012
	print("Request to add skill ", skillName, "to tankman", crewInvID, "as his skill number", skillCount + 1)
	BigWorld.callback(0.1, lambda: BigWorld.player().inventory.freeXPToTankman(crewInvID, xpCoef * (2 ** skillCount), None))
	BigWorld.callback(4, lambda: BigWorld.player().inventory.addTankmanSkill(crewInvID, skillName, None))
	return skillCount + 1

def trainOPCrew(vehicle):
	if not vehicle.isReadyToFight:
		return

	if g_currentVehicle.itemsCache.items.stats.actualFreeXP < 3000000:
		pushErrorMessage("Unlocking is only available for CT. This error message appeared because you have less than 3 000 000 Free XP.")
		return 

	for _, tankman in enumerate(vehicle.crew):
		tankman = tankman[1]
		currentSkills = [skill.name for skill in tankman.skills]
		currentSkillToMaxXP = int(tankman.getNextSkillXpCost() / 5.0 + 1)
		skills = len(currentSkills)
		skillsToLearn = ['brotherhood', 'repair', 'camouflage']
		
		roles = tankman.combinedRoles
		if 'commander' in roles:
			skillsToLearn.append('commander_enemyShotPredictor')
			skillsToLearn.append('commander_eagleEye')
		if 'radioman' in roles:
			skillsToLearn.append('radioman_finder')
		if 'loader' in roles:
			skillsToLearn.append('loader_pedant')

		if currentSkillToMaxXP > 0:
			if tankman.roleLevel < 100 and bool(tankman.skills):
				print("Max level cost: ", currentSkillToMaxXP)
				BigWorld.player().inventory.freeXPToTankman(tankman.invID, currentSkillToMaxXP, None)
				if (tankman.descriptor.lastSkillLevel < 100):
					descr = tankman.descriptor
					lastSkillNumValue = descr.lastSkillNumber - descr.freeSkillsNumber
					nextSkillLevel = descr.lastSkillLevel
					needXp = 0
					for level in xrange(nextSkillLevel, 100):
						needXp += descr.levelUpXpCost(level, lastSkillNumValue)

					currentSkillToMaxXP = int(needXp / 5.0 + 1)
				print("Next XP cost: ", currentSkillToMaxXP)
			BigWorld.player().inventory.freeXPToTankman(tankman.invID, currentSkillToMaxXP, None)

		for skill in skillsToLearn:
			if skill in currentSkills:
				continue
			skills = addCrewSkill(tankman.invID, skill, skills)

	BigWorld.callback(5, lambda: pushInfoMessage("Crew skills trained"))

#endregion

#region Intercepting functions

def interceptVehicleBuy(nationIdx, innationIdx, *args, **kwargs):
	origVehicleBuy(nationIdx, innationIdx, *args, **kwargs)
	itemCD = vehicles.makeIntCompactDescrByID('vehicle', nationIdx, innationIdx)
	researchVehicle(itemCD, 0, lambda: BigWorld.callback(3, lambda: mountTopModules(itemCD)))

def interceptSetResearchButton(self, nation, data):
	data = self._data.dump()
	state = data['nodes'][0]['state']
	if (state & NODE_STATE_FLAGS.LOCKED > 0):
		state = NODE_STATE.remove(state, NODE_STATE_FLAGS.LOCKED)
		state = NODE_STATE.add(state, NODE_STATE_FLAGS.NEXT_2_UNLOCK)
		state = NODE_STATE.add(state, NODE_STATE_FLAGS.ENOUGH_XP)
		data['nodes'][0]['state'] = state
	origSetItems(self, nation, data)

def interceptUnlockItem(self, itemCD, topLevel):
	itemCD = int(itemCD)
	if (isinstance(getItem(itemCD), Vehicle)):
		researchVehicle(int(itemCD))
	else:
		origRequest4Unlock(self, itemCD, topLevel)

#endregion

#region Utils

def processQueue(items, action, interval=1, onCompleted=lambda: None):
	if items is None or len(items) == 0:
		onCompleted()
		return
	item = items.pop(0)
	action(item)
	BigWorld.callback(interval, lambda: processQueue(items, action, interval, onCompleted))

def MYLOG(message=""):
	try:
		print(message)
	except:
		pass
	LOG_NOTE(message)

def pushErrorMessage(text):
	SystemMessages.pushMessage(text, SystemMessages.SM_TYPE.Error)

def pushInfoMessage(text):
	SystemMessages.pushMessage("<b>CT Research:</b><br>{}".format(text), SystemMessages.SM_TYPE.GameGreeting)

def isPlatoonUIVisible():
	platoonCtrl = dependency.instance(IPlatoonController)
	uiLoader = dependency.instance(IGuiLoader)
	pltLayout = platoonCtrl._PlatoonController__ePlatoonLayouts[_EPlatoonLayout.MEMBER]
	platoonWin = uiLoader.windowsManager.getViewByLayoutID(layoutID=pltLayout.layoutID)
	return platoonWin != None and not platoonWin.getParentWindow().isHidden()

#endregion

#region Keyboard controls

import game


old_handler = game.handleKeyEvent
lastTime = time.time()
def new_handler(event):
	isDown, key, mods, _ = game.convertKeyEvent(event)
	KEY_C = 46
	if isPlatoonUIVisible():
		old_handler(event)
		return 

	global lastTime
	if isDown and mods == 0 and key == KEY_C and time.time() - lastTime > 1:
		lastTime = time.time()
		if g_currentVehicle.isPresent():
			trainOPCrew(g_currentVehicle.item)
	old_handler(event)
	return

#endregion

#region Attaching and detaching functions

origRequest4Unlock = None 
origSetItems = None
origVehicleBuy = None

def saveOrigAndAttach():
	if (BigWorld.player() is None or not hasattr(BigWorld.player(), 'shop')):
		BigWorld.callback(5, lambda: saveOrigAndAttach())
		return

	global origRequest4Unlock
	global origSetItems
	global origVehicleBuy
	
	origRequest4Unlock = Research.request4Unlock
	origSetItems =  Research.as_setResearchItemsS
	origVehicleBuy = BigWorld.player().shop.buyVehicle
	attach()

def detach():
	game.handleKeyEvent = old_handler
	Research.as_setResearchItemsS = origSetItems
	Research.request4Unlock = origRequest4Unlock
	BigWorld.player().shop.buyVehicle = origVehicleBuy

def attach():
	game.handleKeyEvent = new_handler
	Research.as_setResearchItemsS = interceptSetResearchButton
	Research.request4Unlock = interceptUnlockItem
	BigWorld.player().shop.buyVehicle = interceptVehicleBuy

saveOrigAndAttach()

#endregion

MYLOG("CT Research loaded")
