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
from gui.Scaleform.framework import ViewTypes
from gui.app_loader.decorators import def_lobby

import unicodedata
import imp
import time


def getItem(itemCD):
	return g_currentVehicle.itemsCache.items.getItemByCD(itemCD)
	
def unlockItem(parentID, idx):
	if g_currentVehicle.itemsCache.items.stats.actualFreeXP < 5000000:
		pushErrorMessage("Unlocking is only available for CT")
		return
	doUnlockItem(parentID, idx)

@decorators.process('research')
def doUnlockItem(parentID, unlockIdx):
	result = yield unlock.UnlockItemProcessor(parentID, unlockIdx, plugins=[]).request()
	MYLOG(result)

def unlockItems(items):
	if items is None or len(items) == 0:
		return
	itemCD, parentID, idx, cost = items.pop(0)
	unlockItem(parentID, idx)
	BigWorld.callback(1, lambda: unlockItems(items))
	
def pushErrorMessage(text):
	SystemMessages.pushMessage(text, SystemMessages.SM_TYPE.Error)

def getVehicleRequirements(intCD, successorCD=0):
	vehItem = getItem(intCD)
	unlockingSequence = []
	if not vehItem.isUnlocked:
		unlockTuple = g_techTreeDP.getUnlockProps(intCD)
		unlockingSequence.extend(getVehicleRequirements(unlockTuple[0], intCD))
		MYLOG("Research {} ({}) for {} XP".format(vehItem.shortUserName, str(intCD), unlockTuple[2]))
	else:
		MYLOG("{} is already researched".format(vehItem.shortUserName))

	researchRequirementsArr = [data for data in vehItem.getUnlocksDescrs()]
	researchRequirements = {}
	for data in researchRequirementsArr:
		researchRequirements[data[2]] = data[3]

	if successorCD != 0:
		for unlockIdx, xpCost, nodeCD, required in researchRequirementsArr:
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
							unlockingSequence.append([itemCD, intCD, itemData[0], itemData[1]])
							requiredCopy.remove(itemCD)
							researched.add(itemCD)
					required = requiredCopy
				
				itemData = [data for data in researchRequirementsArr if data[2]==successorCD][0]
				unlockingSequence.append([successorCD, intCD, itemData[0], itemData[1]])
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
					arr = [nodeCD, intCD, unlockIdx, xpCost]
					if not nodeCD in researched:
						unlockingSequence.append(arr)
						researched.add(nodeCD)
						itemsToBeResearched -= 1

		MYLOG(unlockingSequence)
		unlockItems(unlockingSequence)

	return unlockingSequence

def addCrewSkill(crewInvID, skillName, skillCount):
	xpCoef = 42012
	print("Request to add skill ", skillName, "to tankman", crewInvID, "as his skill number", skillCount + 1)
	BigWorld.callback(0.1, lambda: BigWorld.player().inventory.freeXPToTankman(crewInvID, xpCoef * (2 ** skillCount), None))
	BigWorld.callback(4, lambda: BigWorld.player().inventory.addTankmanSkill(crewInvID, skillName, None))
	return skillCount + 1

def trainOPCrew(vehicle):
	if not vehicle.isReadyToFight:
		return

	if g_currentVehicle.itemsCache.items.stats.actualFreeXP < 5000000:
		pushErrorMessage("Unlocking is only available for CT. This error message appeared because you have less than 5 000 000 Free XP.")
		return 

	for index, tankman in enumerate(vehicle.crew):
		tankman = tankman[1]
		currentSkills = [skill.name for skill in tankman.skills]
		currentSkillToMaxXP = int(tankman.getNextSkillXpCost() / 5.0 + 1)
		skills = len(currentSkills)
		skillsToLearn = ['brotherhood', 'repair', 'camouflage']
		
		roles = tankman.combinedRoles
		if 'commander' in roles:
			skillsToLearn.append('commander_sixthSense')
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

def MYLOG(message=""):
	try:
		print(message)
	except:
		pass
	LOG_NOTE(message)

## Controls

import game


old_handler = game.handleKeyEvent
lastTime = time.time()
def new_handler(event):
	isDown, key, mods, isRepeat = game.convertKeyEvent(event)
	KEY_C = 46
	KEY_R = 19
	deflobby = def_lobby.appLoader.getApp()
	squadWin = deflobby.containerManager.getView(ViewTypes.WINDOW, criteria={POP_UP_CRITERIA.VIEW_ALIAS: PREBATTLE_ALIASES.SQUAD_WINDOW_PY})
	if squadWin and squadWin.isVisible():
		old_handler(event)
		return 

	global lastTime
	if isDown and mods == 0 and key == KEY_R and time.time() - lastTime > 1: # R
		lastTime = time.time()
		if g_currentPreviewVehicle.isPresent():
			getVehicleRequirements(g_currentPreviewVehicle.item.intCD)

	if isDown and mods == 0 and key == KEY_C and time.time() - lastTime > 1: # C
		lastTime = time.time()
		if g_currentVehicle.isPresent():
			trainOPCrew(g_currentVehicle.item)
	old_handler(event)
	return

def detach():
	game.handleKeyEvent = old_handler

game.handleKeyEvent = new_handler
