# -*- coding: utf-8 -*-
"""
Created on Wed Jul  8 15:20:40 2020

@author: lewis
"""
import pandas as pd
import random as rand
import numpy as np




"""Read Player dataset"""
players = pd.read_csv("Players.csv")
champions = pd.read_csv("Champions.csv")
playerChampionPools = pd.read_csv("PlayerChampionPools.csv")
teams = pd.read_csv("Teams.csv")
teamRosters = pd.read_csv("TeamRosters.csv")
championStats = pd.read_csv("ChampionStatistics.csv")
tplayers = len(players.index)

"""Globals"""
LaneName = ["Top Lane","Jungle","Mid Lane","Bot Lane","Support"]
GameBans = []
T1Picks = []
T2Picks = []
ChampionObjects = {}
ElementalDrakePool = 7
GamePlayerRankings = []
FavourableMatchUpMap = {
    "Offence":"Defence",
    "Defence":"Control",
    "Control":"Offence"
}

"""Classes"""
class MyPlayer:
    laneScore = 0
    ChampionPickID = -1

    def __init__(self,Id):
        
        self.comfortBuff = 0
        self.laneScore = 0
        self.matchupAdvantage = 1
        self.ChampionPickID = -1
        self.ID = Id
        rec = players.loc[players['ID']==Id]
        self.name = rec.iloc[0].loc["Name"]
        self.role = rec.iloc[0].loc["Role"]
        self.age = rec.iloc[0].loc["Age"]
        self.aggr = rec.iloc[0].loc["aggr"]
        self.aware = rec.iloc[0].loc["aware"]
        self.pos = rec.iloc[0].loc["pos"]
        self.dmg = rec.iloc[0].loc["dmg"]
        self.cs = rec.iloc[0].loc["cs"]
        self.pool = playerChampionPools.loc[playerChampionPools['PlayerId']==Id]
        self.fightScore = 0
        self.kda = 0
        self.gameRank = 10



    def SetComfort(self):
        pool = self.pool.iloc[0]
        # print("DEBUG SetComfort>>",pool)
        # print("DEBUG SetComfort>>",self.ChampionPickID)
        if (self.ChampionPickID == pool.loc["ChampionId1"]):
            # print("On BEST(tier 1) pick")
            self.comfortBuff = 40
            return
        
        if (self.ChampionPickID == pool.loc["ChampionId2"] or self.ChampionPickID == pool.loc["ChampionId3"]):
            # print("On COMFORT(tier 2) pick")
            self.comfortBuff = 25
            return
        
        if (self.ChampionPickID == pool.loc["ChampionId4"] or self.ChampionPickID == pool.loc["ChampionId5"]):
            # print("On FAMILIAR(tier 3) pick")
            self.comfortBuff = 10
            return
        
        print("Vunerable Pick")
        self.comfortBuff = -10
        return
    
    
    def CheckComfort(self):
        pool = self.pool.iloc[0]
        if self.ChampionPickID == pool.loc["ChampionId1"]:
            # print("On BEST(tier 1) pick")
            return
        
        if self.ChampionPickID == pool.loc["ChampionId2"] or self.ChampionPickID == pool.loc["ChampionId3"]:
            # print("On COMFORT(tier 2) pick")
            return
        
        if self.ChampionPickID == pool.loc["ChampionId4"] or self.ChampionPickID == pool.loc["ChampionId5"]:
            # print("On FAMILIAR(tier 3) pick")
            return
        
        # print("Vunerable Pick")
        return
        
    
    def PrintStats(self):
        print("Name:",self.name)
        print("Age:",self.age)
        print("Champion Pool",self.pool)
    
    def SetMatchupAdvantage(self,adv):
        self.matchupAdvantage = adv
    """Add CalculateLaneScore as a method within class instead"""
    
    """Lane diff can be implemented in here as a method that takes in another player object and subtracting lane scores"""


    
class MyTeam:
    
    
    def __init__(self,teamid,*Id):
        teamRec = (teams.loc[teams['ID']==teamid]).iloc[0]
        focusMap = { "none": -1, "top": 0, "jg": 1, "mid": 2, "bot": 3, "sup": 4 }
        self.id = teamid
        self.name = (teams.loc[teams['ID']==teamid]).iloc[0].loc["Name"]
        self.roster = []
        self.teamComp = []
        self.bans = []
        self.champions = {}
        self.towersTaken = 0
        self.towersRemaining = 11
        self.inhibsExposed = 0
        self.dragsTaken = 0
        self.dragonSoul = False
        self.baronsTaken = 0
        self.rHeraldsTaken = 0
        self.powerPlay = False
        self.totalTeamLaneScore = 0
        self.totalTeamMidGameScore = 0
        self.totalTeamLateGameScore = 0
        self.totalTeamGold = 2500
        self.golddiff = 0
        self.kills = 0
        self.deaths = 0
        self.visionScore = 0
        self.mvp = -1
        self.mvpId = -1
        self.mvpScore = 0
        self.compWinRate = 0.5
        self.compDamageProfileString = ""
        self.compDamageProfile = [5,5] #physical, magic
        self.compTotalDamage = 0
        self.compTotalSturdiness = 0
        self.compTotalCC = 0
        self.compTotalMobility = 0
        self.compTotalUtility = 0
        self.compOverallStrength = ""
        self.compOverallWeakness = ""
        # team style can be used to determine whether the team prioritizes early game aggression, late game scaling or team fighting in their drafting and playstyle. This can be used to give priority to certain stats in the lane score calculations and also to determine which team has the advantage in mid and late game team fight scenarios based on their style and the opposing team's style.
        self.style1 = teamRec.loc["Style1"]
        self.style2 = teamRec.loc["Style2"]
        # focus1 and focus2 can be used to determine which lanes the team prioritizes in terms of drafting and playstyle. This can be used to give lane priority to certain players in the lane score calculations and also to determine which team has the advantage in lane matchups based on their focus and the opposing team's focus.
        self.focus1 = focusMap[teamRec.loc["Focus1"]] #lane focus. values cane be -1:none 0:top, 1:jungle, 2:mid, 3:bot, 4:support
        self.focus2 = focusMap[teamRec.loc["Focus2"]]

        for p in Id:
            """print("[DEBUG]p=",p)"""
            self.roster.append(MyPlayer(p))
            
    def printRoster(self):
        for p in self.roster:
            print(p.PrintStats())
    
    def SetChampionPicks(self,*champIds):
        i=0
        """print('DEBUG SetChampionPicks>> champids',champIds)"""
        for c in champIds:
            self.roster[i].ChampionPickID = c
            self.roster[i].SetComfort()
            i+=1
    
    def SetChampionPicksFromRoster(self):
        i=0
        """print('DEBUG SetChampionPicks>> champids',champIds)"""
        for c in self.teamComp:
            self.roster[i].ChampionPickID = c
            self.roster[i].SetComfort()
            ChampionObjects[c] = MyChampion(c)
            self.compTotalDamage += ChampionObjects[c].Damage
            self.compTotalSturdiness += ChampionObjects[c].Sturdiness
            self.compTotalCC += ChampionObjects[c].CC
            self.compTotalMobility += ChampionObjects[c].Mobility
            self.compTotalUtility += ChampionObjects[c].Utility

            for dmg in range(ChampionObjects[c].Damage):
                self.compDamageProfileString += ChampionObjects[c].DamageType
            i+=1

        #get damage profile
        self.compDamageProfile = [self.compDamageProfileString.count('P'),self.compDamageProfileString.count('M')]

    
    def SetTeamComps(self,*champIds):
        """print('DEBUG SetTeamComps>> champids',champIds)"""
        self.SetChampionPicksFromRoster()
    
    
    
    def SetPicks(self,champIds):
        self.teamComp = []
        for c in champIds:
            
            self.teamComp.append(c)
    
    
    
    def CalculateTeamLaneScores(self):
        for p in self.roster:
            p.laneScore = round(CalculateLaneScore2(p) * p.matchupAdvantage)
            self.totalTeamLaneScore += p.laneScore
            if p.laneScore >self.mvpScore:
                self.mvpScore = p.laneScore
                self.mvp = p.name
                self.mvpId = p.ID
    
    def GetMVP(self):
        mvpscore = 0
        mvp = ""
        mvpId = -1
        for p in self.roster:
            rankCalc = int(p.laneScore * p.kda)
            GamePlayerRankings.append([p.name, rankCalc])
            # print(p.name,"Lane Score:",p.laneScore)
            if rankCalc > mvpscore:
                mvpscore = rankCalc
                mvp = p.name
                mvpId = p.ID
        
        SortedGamePlayerRankings = sorted(GamePlayerRankings, key=lambda x: x[1], reverse=True)
        # print("\nPlayer Rankings:")
        # print(SortedGamePlayerRankings)
        # print("\nPlayer Rankings with Rank Position:")
        for p in self.roster:
            rank = SortedGamePlayerRankings.index([p.name,int(p.laneScore * p.kda)]) + 1
            # print(p.name," [",rank,"] Lane Score:",p.laneScore,"KDA:",round(p.kda,2),"] Total Score:",int(p.laneScore * p.kda))

        self.mvp = mvp
        self.mvpScore = mvpscore
        self.mvpId = mvpId
        return mvp
    
    def OutputTeamGameRankings(self):
        SortedGamePlayerRankings = sorted(GamePlayerRankings, key=lambda x: x[1], reverse=True)
        print("\nPlayer Rankings:")
        print("\nPlayer Rankings with Rank Position:")
        for p in self.roster:
            rank = SortedGamePlayerRankings.index([p.name,int(p.laneScore * p.kda)]) + 1
            p.gameRank = rank
            print(p.name," [",rank,"] Lane Score:",p.laneScore,"KDA:",round(p.kda,2),"] Total Score:",int(p.laneScore * p.kda))

    def GetPlayer(self,Id):
        for x in self.roster:
            if x.ID == Id:
                return x
        
        return -1
    
    def Ban(self,cid):
        self.bans.append(cid)
    
    def Swap(self,pos1,pos2):
        print("swap champion picks")
        temp = self.teamComp[pos1]
        self.teamComp[pos1] = self.teamComp[pos2]
        self.teamComp[pos2] = temp
        
    
    def PrintComp(self):
        print(PrintPicks(self.teamComp))

    def GetTotalGold(self):
        totalgold = 0
        for champ in self.teamComp:
            totalgold += ChampionObjects[champ].Gold
        return totalgold
    
    #sum of all awareness scores and positioning scores multiplied by a randomization factor 
    def GetTeamObjectiveControl(self):
        totalAware = 0
        totalPos = 0
        for p in self.roster:
            totalAware += p.aware
            totalPos += p.pos
        return (totalAware + totalPos) * rand.randint(1,3)
    
    def GetCompositionWinRate(self):
        totalWinRate = 0
        for champ in self.teamComp:
            totalWinRate += ChampionObjects[champ].WinRate
        return round(totalWinRate / len(self.teamComp), 2)
    
    def GetCompositionDamageProfile(self):
        return self.compDamageProfile
        
    

class MyChampion:
    def __init__(self,Id):
        """rec = champions.loc[champions['Id']==Id]"""
        rec = champions[(champions['Id'] == Id)]
        self.ID = Id
        self.Name = (champions.loc[champions['Id']==Id]).iloc[0].loc["Name"]
        self.Class = rec.iloc[0].loc["Class"]
        self.Style = rec.iloc[0].loc["Style"]
        self.Difficulty = rec.iloc[0].loc["Difficulty"]
        self.DamageType = rec.iloc[0].loc["DamageType"]
        self.Damage = rec.iloc[0].loc["Damage"]
        self.Sturdiness = rec.iloc[0].loc["Sturdiness"]
        self.CC = rec.iloc[0].loc["Crowd-Control"]
        self.Mobility = rec.iloc[0].loc["Mobility"]
        self.Utility = rec.iloc[0].loc["Utility"]
        self.Offence = (self.Damage + self.Mobility)
        self.Defence = (self.Sturdiness + self.CC)
        self.Control = (self.Utility + self.CC)
        self.ChampionStrength = "Offence" if self.Offence >= self.Defence and self.Offence >= self.Control else "Defence" if self.Defence >= self.Offence and self.Defence >= self.Control else "Control"
        self.ChampionWeakness = [k for k, v in FavourableMatchUpMap.items() if v == self.ChampionStrength][0]
        self.Kills = 0
        self.Deaths = 0
        self.Assists = 0
        self.Gold = 0
        self.CS = 0
        self.GameStats = {
            'DamageDealt': 0,
            'DamageTaken': 0
        }
        self.WinRate = (championStats.loc[championStats['Champion']==self.Name]).iloc[0].loc["WinRate"]
        self.PickRate = (championStats.loc[championStats['Champion']==self.Name]).iloc[0].loc["PickRate"]
        self.kda = 0.0

    def PrintStats(self):
        print("ID:",self.ID)
        print("Name:",self.Name)

class FightChampStats:
    def __init__(self):
        self.Dificulty = 0
        self.DamageType = ""
        self.Damage = 0
        self.MagicDamage = 0
        self.PhysicalDamage = 0
        self.Sturdiness = 0
        self.CC = 0
        self.Mobility = 0
        self.Utility = 0


"""********FUNCTION DEFINITIONS********"""

def CalculateLaneScore2(p):
    champ = MyChampion(p.ChampionPickID)
    champAggrSyn = (champ.Damage*30 + champ.Sturdiness*30 + champ.CC*10 + champ.Mobility*10 + champ.Utility*20)/200
    champAwrSyn = (champ.Damage*10 + champ.Sturdiness*30 + champ.CC*20 + champ.Mobility*10 + champ.Utility*30)/200
    champPosSyn = (champ.Damage*30 + champ.Sturdiness*20 + champ.CC*10 + champ.Mobility*30 + champ.Utility*10)/200
    champDmgSyn = (champ.Damage*40 + champ.Sturdiness*10 + champ.CC*10 + champ.Mobility*40 + champ.Utility*20)/200
    
    print("DEBUG CalculateLaneScore2>>",p.name,"on",champ.Name)
    print("DEBUG CalculateLaneScore2>>","Aggression Syn:",round(champAggrSyn,2),"Awareness Syn:",round(champAwrSyn,2),"Positioning Syn:",round(champPosSyn,2),"Damage Syn:",round(champDmgSyn,2))
    
    aggr = rand.randint(1,10) * p.aggr
    aware = rand.randint(1,10) * p.aware
    pos = rand.randint(1,10) * p.pos
    dmg = rand.randint(1,10) * p.dmg

    print("DEBUG CalculateLaneScore2>>","Aggression:",aggr,"Awareness:",aware,"Positioning:",pos,"Damage:",dmg)
    
    score = (aggr*champAggrSyn + aware*champAwrSyn + pos*champPosSyn + dmg*champDmgSyn)
    score = score + (score * p.comfortBuff)

    return max(score, 100)
        



"""Takes lane scores and opposing lane players"""

def SetChampionLaneMatchupAdvantage(p1,p2):
    champ1 = ChampionObjects[p1.ChampionPickID]
    champ2 = ChampionObjects[p2.ChampionPickID]
    advantage_champion = None
    advantage_player = None
    disadvantage_champion = None
    disadvantage_player = None

    if champ1.ChampionStrength == champ2.ChampionWeakness:
        advantage_champion = champ1
        advantage_player = p1
        disadvantage_champion = champ2
        disadvantage_player = p2
    elif champ2.ChampionStrength == champ1.ChampionWeakness:
        advantage_champion = champ2
        advantage_player = p2
        disadvantage_champion = champ1
        disadvantage_player = p1
   
    # print("DEBUG SetChampionLaneMatchupAdvantage>>",champ1.Name,champ1.ChampionStrength,getattr(champ1, champ1.ChampionStrength)," VS ",champ2.Name,champ2.ChampionStrength,getattr(champ2, champ2.ChampionStrength))
    # print("DEBUG SetChampionLaneMatchupAdvantage>> Advantage:",advantage_champion.Name if advantage_champion is not None else "None","Disadvantage:",disadvantage_champion.Name if disadvantage_champion is not None else "None")
    if advantage_champion is not None:
        diff = getattr(advantage_champion, advantage_champion.ChampionStrength) - getattr(disadvantage_champion, disadvantage_champion.ChampionWeakness)
        # severity = ""
        if diff >= 2:
            # severity = "Strongly"
            advantage_player.SetMatchupAdvantage(1.5)
        else:
            # severity = "Slightly"
            advantage_player.SetMatchupAdvantage(1.25)

        # print("DEBUG SetChampionLaneMatchupAdvantage>>",advantage_champion.Name,"has a",severity,"favourable matchup against",disadvantage_champion.Name)

def CheckChampionLaneMatchup(p1,p2):
    champ1 = ChampionObjects[p1.ChampionPickID]
    champ2 = ChampionObjects[p2.ChampionPickID]
    advantage_champion = None
    advantage_player = None

    # print("DEBUG CheckChampionLaneMatchup>>",champ1.Name,champ1.ChampionStrength,getattr(champ1, champ1.ChampionStrength)," VS ",champ2.Name,champ2.ChampionStrength,getattr(champ2, champ2.ChampionStrength))
    if p1.matchupAdvantage > p2.matchupAdvantage:
        advantage_champion = champ1
        advantage_player = p1
    elif p2.matchupAdvantage > p1.matchupAdvantage:
        advantage_champion = champ2
        advantage_player = p2

    if advantage_champion is not None:
        severity = ""
        if  advantage_player.matchupAdvantage == 1.5:
            severity = "Strongly"
        else:
            severity = "Slightly"
        return "Favours " + advantage_champion.Name + " " + str(severity) + " in lane."
    
    return "Even Matchup"

def PrintMatchup(p1,p2):
    p1ChampName = (champions.loc[champions['Id']==p1.ChampionPickID]).iloc[0].loc["Name"]
    p2ChampName = (champions.loc[champions['Id']==p2.ChampionPickID]).iloc[0].loc["Name"]
    print("Lane Matchup:",p1.name,"as",p1ChampName,"VS",p2.name,"as",p2ChampName)
    print(CheckChampionLaneMatchup(p1,p2))

def GetChampName(cid):
    champName = (champions.loc[champions['Id']==cid]).iloc[0].loc["Name"]
    return champName


def Ban(t,cid):
    t.Ban(cid)
    print(t.name,"Bans",GetChampName(cid))
    GameBans.append(cid)
    
def GetGameBans():
    print(GameBans)
    
def Pick(picks,pick):
    picks.append(pick)
    PrintPicks(picks)
    
def PrintPicks(picks):
    pickNames =[]
    for p in picks:
        pickNames.append(GetChampName(p))
    print(pickNames)
    

def CalculateLaneScore(*player):
    resultset = []
    for p in player:
        """roll player lane score(random number * stat factor)"""
        """p1LaneScore = (rand.randint(1,10)*players.loc[p,'aggr']) + (rand.randint(1,10) * players.loc[p,'aware']) + (rand.randint(1,10)*players.loc[p,'pos']) + (rand.randint(1,10)*players.loc[p,'dmg'])"""
        p1LaneScore = (rand.randint(1,10)*p.aggr) + (rand.randint(1,10) * p.aware) + (rand.randint(1,10)*p.pos) + (rand.randint(1,10)*p.dmg)
        resultset.append(p1LaneScore)

    return resultset



"""DO NOT USE. OUTDATED METHOD FOR FUTURE REFERENCE ONLY"""
def CalculateLaneCSDiffs(laneScores,p1,p2):
    p1gold = (laneScores[0]*10) + p1.cs*10
    p2gold = (laneScores[1]*10) + p2.cs*10
    
    """part of original calculation in case absolute value returned is an issue"""
    """p1gdiff = p1gold - p2gold
    p2gdiff = p2gold - p1gold"""
    
    """gold differencial @ 15 minutes"""
    gdiff = abs(p1gold - p2gold)
    return gdiff

"""Takes lane scores and opposing lane players"""
def CalculateLaneCSDiffsAll(t1,t2):
    gdiffs = []
    for i in range(0,len(t1.roster)):
        p1 = t1.roster[i]
        p2 = t2.roster[i]
        p1gold = int((p1.laneScore*1) + p1.cs*10)
        p2gold = int((p2.laneScore*1) + p2.cs*10)
        gdiff = abs(p1gold - p2gold)
        gdiffs.append(gdiff)
    """part of original calculation in case absolute value returned is an issue"""

    
    """list of gold differencials @ 15 minutes"""    
    return gdiffs

def SimulatePlayerFightPerformance(p,t1fightstats):
    comfortBuff = p.comfortBuff
    champion = (champions.loc[champions['Id']==p.ChampionPickID]).iloc[0]
    # team1combatantscomp.append(champion)
    # team1combatantscompnames.append(champion.loc["Name"])
    championObj = ChampionObjects[p.ChampionPickID]

    champdamage = champion.loc["Damage"]
    champdamagetype = champion.loc["DamageType"]
    champdifficulty = champion.loc["Difficulty"]
    champsturdiness = champion.loc["Sturdiness"]
    champcc = champion.loc["Crowd-Control"]
    champmobility = champion.loc["Mobility"]
    champutility = champion.loc["Utility"]
    champstyle = champion.loc["Style"]
    champgold = championObj.Gold
    champmagicdamage = champdamage * (champion.loc["Style"] * 10)
    champphysicaldamage = champdamage * abs(10 - champion.loc["Style"] * 10)
    totaldamage = champmagicdamage + champphysicaldamage

    performancescore = (p.laneScore + champgold) / 2

    #roll for performance score modifer. Calculation would be based on the comforrtBuff, Champion Difficulty and a skill check
    minplayerimpact = p.comfortBuff
    maxplayerimpact = abs(p.comfortBuff * champdifficulty)
    skillcheck = rand.randint(minplayerimpact, maxplayerimpact)

    performancescore = performancescore + (performancescore * (skillcheck / 100)) 

    t1fightstats.Dificulty += champion.loc["Difficulty"]
    t1fightstats.DamageType += champion.loc["DamageType"]

    t1fightstats.Damage += (totaldamage/2) * (performancescore) / 20
    t1fightstats.Sturdiness += champsturdiness * (performancescore)

    t1fightstats.CC += (champcc * 30) + ((champcc * 30) * (maxplayerimpact)) / 100
    t1fightstats.Mobility += (champmobility * 30) + ((champmobility * 30) * (maxplayerimpact)) / 100
    t1fightstats.Utility += (champutility * 30) + ((champutility *30) * (maxplayerimpact)) / 100

    # print(p.name,"on",champion.loc["Name"],"has entered the fight")
    # print("Form",p.laneScore,"Gold",champgold)
    # print("Champ Difficulty:",champdifficulty,"Min Player Impact:",comfortBuff,"Max Player Impact:",maxplayerimpact,"Skill Check roll:",skillcheck)

    #Update player lane score based on fight performance
    p.laneScore = performancescore
    championObj.GameStats['DamageDealt'] += t1fightstats.Damage
    championObj.GameStats['DamageTaken'] += t1fightstats.Sturdiness

    return performancescore

def SimulateFight(t1,t2,numteam1combatants,numteam2combatants,engagedby):
    print("Simulating Fight")
    team1combatants = []
    team1combatantscomp = []
    team1combatantscompnames = []
    team2combatants = []
    team2combatantscomp = []
    team2combatantscompnames = []
    # engagedby = rand.randint(1,2)
    t1skirmishscore = 0
    t2skirmishscore = 0
    team1combatmodifiers = 0
    team2combatmodifiers = 0
    t1fightstats = FightChampStats()
    t2fightstats = FightChampStats()

    print(numteam1combatants, " vs ",numteam2combatants)

    roster1 = t1.roster
    roster2 = t2.roster
    team1combatants = rand.sample(roster1,numteam1combatants)
    team2combatants = rand.sample(roster2,numteam2combatants)

    t1killdist = []
    t2killdist = []
    t1deathdist = []
    t2deathdist = []
    t1killprob = []
    t2killprob = []
    t1deathprob = []
    t2deathprob = []
    t1totalfightscore = 0
    t2totalfightscore = 0

    for p in team1combatants:
        champion = (champions.loc[champions['Id']==p.ChampionPickID]).iloc[0]
        team1combatantscomp.append(champion)
        team1combatantscompnames.append(champion.loc["Name"])
        p.fightScore = SimulatePlayerFightPerformance(p,t1fightstats)
        t1totalfightscore += int(p.fightScore)
        t1killdist.append([champion.loc["Id"],p.fightScore,0])
    
    for p in team2combatants:
        champion = (champions.loc[champions['Id']==p.ChampionPickID]).iloc[0]
        team2combatantscomp.append(champion)
        team2combatantscompnames.append(champion.loc["Name"])
        p.fightScore = SimulatePlayerFightPerformance(p,t2fightstats)
        t2totalfightscore += int(p.fightScore)
        t2killdist.append([champion.loc["Id"],p.fightScore,0])

    for rec in t1killdist:
        t1deathdist.append([rec[0],t1totalfightscore - rec[1]])
        #get the inverse of the kill score to determine the death probability
        prob = t1totalfightscore - rec[1]
        mult = numteam1combatants - 1 if numteam1combatants > 1 else 1
        probspace = t1totalfightscore * (mult)
        t1deathprob.append((prob / probspace))

    for rec in t2killdist:
        t2deathdist.append([rec[0],t2totalfightscore - rec[1]])
        #get the inverse of the kill score to determine the death probability
        # deathscore = t2totalfightscore - rec[1]
        prob = t2totalfightscore - rec[1]
        mult = numteam2combatants - 1 if numteam2combatants > 1 else 1
        probspace = t2totalfightscore * (mult)
        t2deathprob.append((prob / probspace))

    #normalize the death probabilities
    t1deathprob = np.asarray(t1deathprob)#.astype('float64')
    t1deathprob /= t1deathprob.sum()
    t2deathprob = np.asarray(t2deathprob)#.astype('float64')
    t2deathprob /= t2deathprob.sum()
    
    #calculate fight scores to determine winner
    team1combatmodifiers = (t1fightstats.CC/numteam1combatants + t1fightstats.Mobility/numteam1combatants + t1fightstats.Utility/numteam1combatants) / 3
    team2combatmodifiers = (t2fightstats.CC/numteam2combatants + t2fightstats.Mobility/numteam2combatants + t2fightstats.Utility/numteam2combatants) / 3
    team1modifieddamage = t1fightstats.Damage * team1combatmodifiers
    team2modifieddamage = t2fightstats.Damage * team2combatmodifiers
    team1modifiedsturdiness = t1fightstats.Sturdiness * team1combatmodifiers
    team2modifiedsturdiness = t2fightstats.Sturdiness * team2combatmodifiers
    t1skirmishscore = team1modifieddamage - team2modifiedsturdiness
    t2skirmishscore = team2modifieddamage - team1modifiedsturdiness
    execution_diff = abs(t1skirmishscore - t2skirmishscore) / 1000000

    # print("team1 fight damage:",t1fightstats.Damage,"team1 fight sturdiness:",t1fightstats.Sturdiness,"team1 fight cc:",t1fightstats.CC,"team1 fight mobility:",t1fightstats.Mobility,"team1 fight utility:",t1fightstats.Utility)
    # print("team1fightstats:",t1fightstats.Dificulty,t1fightstats.DamageType,t1fightstats.Damage,t1fightstats.MagicDamage,t1fightstats.PhysicalDamage,t1fightstats.Sturdiness,t1fightstats.CC,t1fightstats.Mobility,t1fightstats.Utility)
    # print("team1 mofiifers:",team1combatmodifiers,"team2 modifiers:",team2combatmodifiers)
    # print("team1 modified damage:",team1modifieddamage,"team2 modified damage:",team2modifieddamage)
    # print("team1 modified sturdiness:",team1modifiedsturdiness,"team2 modified sturdiness:",team2modifiedsturdiness)

    # print("team2 fight damage:",t2fightstats.Damage,"team2 fight sturdiness:",t2fightstats.Sturdiness,"team2 fight cc:",t2fightstats.CC,"team2 fight mobility:",t2fightstats.Mobility,"team2 fight utility:",t2fightstats.Utility)
    # print("team2fightstats:",t2fightstats.Dificulty,t2fightstats.DamageType,t2fightstats.Damage,t2fightstats.MagicDamage,t2fightstats.PhysicalDamage,t2fightstats.Sturdiness,t2fightstats.CC,t2fightstats.Mobility,t2fightstats.Utility)

    print(t1.name,"has engaged a skirmish")
    print(t1.name,team1combatantscompnames,"engaged on",t2.name,team2combatantscompnames)
    # print("execution_scores:",t1.name,"=",t1skirmishscore,"vs",t2.name,"=",t2skirmishscore)
    # print("execution diff:", execution_diff)

    t1kills = 0
    t2kills = 0
    t1killson = []
    t2killson = []
    t1deathson = []
    t2deathson = []
    t1survived = []
    t2survived = []

    if(t1skirmishscore > t2skirmishscore):
        print(t1.name,"has won the skirmish")

        #calculate t1 kills
        if execution_diff > numteam2combatants:
            t1kills = numteam2combatants
            t2kills = 0
        elif execution_diff > 1:
            t1kills = int(execution_diff)
            t2kills = rand.randint(0, t1kills)
            # t2kills = rand.randint(0, round(numteam1combatants - execution_diff))
        else:
            t1kills = 1
            t2kills = 1
        if(t1kills > 0):
            print(t1.name,"has killed",t1kills,"of",t2.name,"players")
        if(t2kills > 0):
            print(t2.name,"has killed",t2kills,"of",t1.name,"players")
        t1.kills += t1kills
        t2.kills += t2kills

        t1survived = []
        t1fightlist = []
        for p in team1combatants:
            t1survived.append(p.ChampionPickID)
            t1fightlist.append(p.ChampionPickID)
        t2survived = []
        t2fightlist = []
        for p in team2combatants:
            t2survived.append(p.ChampionPickID)
            t2fightlist.append(p.ChampionPickID)
        
        
        # print("t1survived:",t1survived)
        # print("t2survived:",t2survived)

        for i in range(t1kills):
            killcredit = RollCustomProbablity(t1killdist,t1totalfightscore)
            deathcredit = -1

            #kepp rolling until a unique death credit is found
            while deathcredit not in t2survived:
                deathcredit = np.random.choice(t2fightlist, 1, replace=True, p=t2deathprob)[0]
                if deathcredit in t2survived:
                    t2survived.remove(deathcredit)
                    break

            t1killson.append(killcredit)
            t2deathson.append(deathcredit)
            # print(killcredit,deathcredit)
            # print("Kill Credit:",ChampionObjects[killcredit].Name,"Death Credit:",ChampionObjects[deathcredit].Name)
            print(ChampionObjects[killcredit].Name,"has slain",ChampionObjects[deathcredit].Name)

        for i in range(t2kills):
            killcredit = RollCustomProbablity(t2killdist,t2totalfightscore)
            deathcredit = -1

            #kepp rolling until a unique death credit is found
            while deathcredit not in t1survived:
                deathcredit = np.random.choice(t1fightlist, 1, replace=True, p=t1deathprob)[0]
                if deathcredit in t1survived:
                    t1survived.remove(deathcredit)
                    break

            t2killson.append(killcredit)
            t1deathson.append(deathcredit)
            # print("Kill Credit:",ChampionObjects[killcredit].Name,"Death Credit:",ChampionObjects[deathcredit].Name)
            print(ChampionObjects[killcredit].Name,"has slain",ChampionObjects[deathcredit].Name)

        t1.totalTeamMidGameScore += 1*numteam2combatants

    elif(t2skirmishscore > t1skirmishscore):
        print(t2.name,"has won the skirmish")

        #calculate t2 kills
        if execution_diff > numteam1combatants:
            t2kills = numteam1combatants
            t1kills = 0
        elif execution_diff > 1:
            t2kills = int(execution_diff)
            t1kills = rand.randint(0, t2kills)
            # t1kills = rand.randint(0, round(numteam2combatants - execution_diff))
        else:
            t2kills = 1
            t1kills = 1
        print(t2.name,"has killed",t2kills,"of",t1.name,"players")
        print(t1.name,"has killed",t1kills,"of",t2.name,"players")
        t2.kills += t2kills
        t1.kills += t1kills

        t1survived = []
        t1fightlist = []
        for p in team1combatants:
            t1survived.append(p.ChampionPickID)
            t1fightlist.append(p.ChampionPickID)
        t2survived = []
        t2fightlist = []
        for p in team2combatants:
            t2survived.append(p.ChampionPickID)
            t2fightlist.append(p.ChampionPickID)

        # print("t1survived:",t1survived)
        # print("t2survived:",t2survived)

        for i in range(t2kills):
            killcredit = RollCustomProbablity(t2killdist,t2totalfightscore)
            deathcredit = -1

            while deathcredit not in t1survived:
                deathcredit = np.random.choice(t1fightlist, 1, replace=True, p=t1deathprob)[0]
                if deathcredit in t1survived:
                    t1survived.remove(deathcredit)
                    break

            t2killson.append(killcredit)
            t1deathson.append(deathcredit)
            # print("Kill Credit:",ChampionObjects[killcredit].Name,"Death Credit:",ChampionObjects[deathcredit].Name)
            print(ChampionObjects[killcredit].Name,"has slain",ChampionObjects[deathcredit].Name)

        for i in range(t1kills):
            killcredit = RollCustomProbablity(t1killdist,t1totalfightscore)
            deathcredit = -1

            # print("t2deathprob:",t2deathprob)
            # print(sum(t2deathprob))

            while deathcredit not in t2survived:
                deathcredit = np.random.choice(t2fightlist, 1, replace=True, p=t2deathprob)[0]
                if deathcredit in t2survived:
                    t2survived.remove(deathcredit)
                    break

            t1killson.append(killcredit)
            t2deathson.append(deathcredit)
            # print("Kill Credit:",ChampionObjects[killcredit].Name,"Death Credit:",ChampionObjects[deathcredit].Name)
            print(ChampionObjects[killcredit].Name,"has slain",ChampionObjects[deathcredit].Name)

        t2.totalTeamMidGameScore += 1*numteam1combatants

    else:
        print("The skirmish has ended even")
        t1.totalTeamMidGameScore += 0.5*numteam2combatants
        t2.totalTeamMidGameScore += 0.5*numteam1combatants

    for p in team1combatants:
        champion = ChampionObjects[p.ChampionPickID]
        killsinfight = t1killson.count(p.ChampionPickID)
        assistsinfight = t1kills - killsinfight
        champion.Kills += killsinfight
        champion.Assists += assistsinfight
        if(t1deathson.count(p.ChampionPickID) > 0):
            champion.Deaths += 1
        killgold = 300 * killsinfight
        assistgold = 150 * assistsinfight
        champion.Gold += killgold + assistgold
        champion.kda = (champion.Kills + champion.Assists) / max(1, champion.Deaths)
        p.kda = champion.kda
        # print(champion.Name,champion.Kills,"/",champion.Deaths,"/",champion.Assists)

    for p in team2combatants:
        champion = ChampionObjects[p.ChampionPickID]
        killsinfight = t2killson.count(p.ChampionPickID)
        assistsinfight = t2kills - killsinfight
        champion.Kills += killsinfight
        champion.Assists += assistsinfight
        if(t2deathson.count(p.ChampionPickID) > 0):
            champion.Deaths += 1
        killgold = 300 * killsinfight
        assistgold = 150 * assistsinfight
        champion.Gold += killgold + assistgold
        champion.kda = (champion.Kills + champion.Assists) / max(1, champion.Deaths)
        p.kda = champion.kda
        # print(champion.Name,champion.Kills,"/",champion.Deaths,"/",champion.Assists)

"""Simulate an early game phase (Minute 0-15)"""
def SimulateEarlyGame(t1,t2,goldDiffList):
    teamarr = [t1,t2]
    print("\n\nEarly game Phase")
    # print("Towers, Drags, Barons, and Rift Heralds taken")
    # print("Objective control")
    # print("Vision control")
    # print("Jungle control")
    # print("Early game picks")
    SetEarlyGameChampStates(t1,t2,goldDiffList)
    print(t1.name,"Early game Score:",t1.totalTeamLaneScore,"|",t2.name,"Early game Score:",t2.totalTeamLaneScore)

    """Objective control"""
    #dragons
    RollDragons(t1,t2,3)
    #towers
    RollTowers(t1,t2,5)
    """Teamfights. Generate a random number to determine the number of teamfights. Then simulate each teamfight using a combination of the each team's lane scores, gold leads, vision control and champion attributes to determine the winner"""
    # print("Teamfights")
    teamfights = rand.randint(0,3)

    """Skirmishes. Generate one random number to determine the number of skirmishes, 2 numbers representing the number of players involved for each team. Then simulate each skirmish using a combination of the each team's lane scores, gold leads, and vision control to determine the winner"""
    print("Skirmishes")
    skirmishes = rand.randint(0,10)
    for i in range(0,skirmishes):
        print("Skirmish ",i+1)
        numteam1combatants = rand.randint(1,4)
        numteam2combatants = rand.randint(1,numteam1combatants)
        engagedby = rand.randint(1,2)
        if engagedby == 1:
            SimulateFight(t1,t2,numteam1combatants,numteam2combatants,engagedby)
        else:
            SimulateFight(t2,t1,numteam1combatants,numteam2combatants,engagedby)

    """Solo kills"""
    # print("Solo kills")
    
    # print("Gold leads")
    # print("Objective control")
    # print("Vision control")
    # print("Jungle control")
    # print("Early game picks")
    print(t1.name,"Early game Score:",t1.totalTeamMidGameScore,"|",t2.name,"Early game Score:",t2.totalTeamMidGameScore)

"""Simulate a mid game phase (Minute 15-25)"""
def SimulateMidGame(t1,t2,goldDiffList):
    teamarr = [t1,t2]
    print("\n\nMid game Phase")
    # print("Towers, Drags, Barons, and Rift Heralds taken")

    #update cs for players

    """Objective control"""
    #dragons
    RollDragons(t1,t2,2)

    #barons
    RollBarons(t1,t2,1)
    
    #towers
    RollTowers(t1,t2,6)
    """Teamfights. Generate a random number to determine the number of teamfights. Then simulate each teamfight using a combination of the each team's lane scores, gold leads, vision control and champion attributes to determine the winner"""
    # print("Teamfights")
    teamfights = rand.randint(0,3)


    """Skirmishes. Generate one random number to determine the number of skirmishes, 2 numbers representing the number of players involved for each team. Then simulate each skirmish using a combination of the each team's lane scores, gold leads, and vision control to determine the winner"""
    print("Skirmishes")
    skirmishes = rand.randint(0,10)
    for i in range(0,skirmishes):
        print("Skirmish ",i+1)
        numteam1combatants = rand.randint(2,5)
        numteam2combatants = rand.randint(1,numteam1combatants)
        engagedby = rand.randint(1,2)
        if engagedby == 1:
            SimulateFight(t1,t2,numteam1combatants,numteam2combatants,engagedby)
        else:
            SimulateFight(t2,t1,numteam1combatants,numteam2combatants,engagedby)

    
    """Solo kills"""
    # print("Solo kills")
    
    # print("Gold leads")
    # print("Objective control")
    # print("Vision control")
    # print("Jungle control")
    # print("Midgame picks")
    print(t1.name,"Midgame Score:",t1.totalTeamMidGameScore,"|",t2.name,"Midgame Score:",t2.totalTeamMidGameScore)

"""Simulate a lategame phase (Minute 25-35)"""
def SimulateLateGame():
    print("Lategame Phase")
    print("Towers, Drags, Barons, and Rift Heralds taken")
    print("Teamfights")
    print("Skirmishes")
    print("Solo kills")
    print("Gold leads")
    print("Objective control")
    print("Vision control")
    print("Jungle control")
    print("Lategame picks")

def SetEarlyGameChampStates(t1,t2,goldDiffList):
    teamarr = [t1,t2]
    for i in range(0,len(t1.roster)):
        # print("Lane:",LaneName[i])
        # print("Gold diff:",goldDiffList[i])
        for j in (0,1):
            num = 1 - j
            lanediff = teamarr[j].roster[i].laneScore - teamarr[num].roster[i].laneScore
            modifier = 0
            # print("Lane diff:",lanediff)
            if lanediff > 500:
                modifier = 1.5
            elif lanediff > 250:
                modifier = 1
            elif lanediff < -250:
                modifier = -1
            elif lanediff < -500:
                modifier = -1.5
            else:
                modifier = 0

            player = teamarr[j].roster[i]
            champ = ChampionObjects[player.ChampionPickID]
            # champ = (champions.loc[champions['Id']==player.ChampionPickID]).iloc[0]
            champcs = player.cs * 15
            champ.CS = champcs

            #if lane is support (lane 4) then reduce cs by 85%
            if i == 4:
                champ.CS = champ.CS * 0.15

            gold = champcs * 19.8

            if(lanediff > 0):
                gold += goldDiffList[i]

            champ.Gold = gold
            teamarr[j].totalTeamGold += gold
            # print(player.name,"on",champ.loc["Name"],"CS:",champ.loc["CS"])
            # print("Gold:",champ.loc["Gold"])
        

    
"""DO NOT USE. OUTDATED METHOD FOR FUTURE REFERENCE ONLY"""
def OutputResults(ls,p1,p2,diff):
    print(p1.name," got a lane score of ",p1.laneScore)
    print(p2.name," got a lane score of ",p2.laneScore)
    if p1.laneScore > p2.laneScore:
        print(p1.name," Has won the lane with a gold lead of ",diff)
    elif p2.laneScore > p1.laneScore:
        print(p2.name," Has won the lane with a gold lead of ",diff)
    else:
        print("The lane phase has ended even")
        


def OutputLaneResults(t1,t2,diff):
    
    for lane in range(0,len(t1.roster)):
        p1 = t1.roster[lane]
        p2 = t2.roster[lane]
        
        print(LaneName[lane],"==============================================")
        SetChampionLaneMatchupAdvantage(p1,p2)
        PrintMatchup(p1,p2)
        print(p1.name," got a lane score of ",p1.laneScore)
        print(p2.name," got a lane score of ",p2.laneScore)
        
        if p1.laneScore > p2.laneScore:
            print(p1.name," Has won the lane with a gold lead of ",diff[lane],"\n")
        elif p2.laneScore > p1.laneScore:
            print(p2.name," Has won the lane with a gold lead of ",diff[lane],"\n")
        else:
            print("The lane phase has ended even\n")

    print("=======================================================")
    print(t1.name,"Gold:",t1.totalTeamGold,"|",t2.name,"Gold:",t2.totalTeamGold)

    goldlead = abs(t1.totalTeamGold - t2.totalTeamGold)

    if t1.totalTeamGold > t2.totalTeamGold:
        print(t1.name,"Has a gold lead of",round(goldlead/1000,1),"K at 15 minutes")
    elif t2.totalTeamGold > t1.totalTeamGold:
        print(t2.name,"Has a gold lead of",round(goldlead/1000,1),"K at 15 minutes")
    else:
        print("The game is dead even at 15 minutes")

#function updates all champions CS based on the current game time and player cs stats
def UpdateCS(t1,t2,gametime):
    for i in range(0,len(t1.roster)):
        player1 = t1.roster[i]
        player2 = t2.roster[i]
        champ1 = ChampionObjects[player1.ChampionPickID]
        champ2 = ChampionObjects[player2.ChampionPickID]
        prevcs1 = champ1.CS
        prevcs2 = champ2.CS
        cs1 = player1.cs * gametime
        cs2 = player2.cs * gametime
        
        if(i == 4):
            cs1 = cs1 * 0.15
            cs2 = cs2 * 0.15
        
        gainedcs1 = cs1 - prevcs1
        gainedcs2 = cs2 - prevcs2

        champ1.CS = round(cs1)
        champ2.CS = round(cs2)

        champ1.Gold += gainedcs1 * 19.8
        champ2.Gold += gainedcs2 * 19.8

#function that calulates lane gaps
def CalculateLaneGaps(t1,t2):
    lanegaps = [0,0,0,0,0]
    for i in range(0,len(t1.roster)):
        p1 = t1.roster[i]
        p2 = t2.roster[i]
        #get lane assistance score from other lanes. loops through all other lanes and adds a percentage of their lane score to the current lane score(50% if jg, 25% if support and current lane isn't bot, 10% otherwise).
        for j in range(0,len(t1.roster)):
            if(j != i):
                p3 = t1.roster[j]
                p4 = t2.roster[j]
                if(j == 1):
                    p1.laneScore += p3.laneScore * 0.45
                    p2.laneScore += p4.laneScore * 0.45
                elif(j == 5 and i == 4):
                    p1.laneScore += p3.laneScore * 0.5
                    p2.laneScore += p4.laneScore * 0.5
                else:
                    p1.laneScore += p3.laneScore * 0.10
                    p2.laneScore += p4.laneScore * 0.10

        lanegaps[i] = p1.laneScore - p2.laneScore
    print("Lane Gaps:",lanegaps)
    return lanegaps

def PrintTeamStats(t1,t2):
    print(t1.name,"\t\t\t",t2.name)
    print(t1.teamComp,"\t\t\t",t2.teamComp)
    print(t1.towersTaken,"\t\t\t",t2.towersTaken)
    print(t1.dragsTaken,"\t\t\t",t2.dragsTaken)
    print(t1.baronsTaken,"\t\t\t",t2.baronsTaken)
    print(t1.totalTeamLaneScore,"\t\t\t",t2.totalTeamLaneScore)

def PrintGameStats(t1,t2):
    print("===============================================")
    print(t1.name,"\t\t\t",t2.name)
    print("Kills:",t1.kills,"\t\t\t\t Kills",t2.kills)
    print("Gold:",t1.GetTotalGold(),"\t\t\t\t Gold",t2.GetTotalGold())
    print("Towers:",t1.towersTaken,"\t\t\t\t Towers",t2.towersTaken)
    print("Drags:",t1.dragsTaken,"\t\t\t\t Drags",t2.dragsTaken)
    print("Drag Soul:",t1.dragonSoul,"\t\t\t Drag Soul",t2.dragonSoul)
    print("Barons:",t1.baronsTaken,"\t\t\t\t Barons",t2.baronsTaken)
    for i in range(0,len(t1.roster)):
        p1 = t1.roster[i]
        p2 = t2.roster[i]
        champ1 = ChampionObjects[p1.ChampionPickID]
        champ2 = ChampionObjects[p2.ChampionPickID]
        print(champ1.Name,champ1.CS,champ1.Kills,"/",champ1.Deaths,"/",champ1.Assists,"\t\t\t",champ2.Name,champ2.CS,champ2.Kills,"/",champ2.Deaths,"/",champ2.Assists)
    print("===============================================")

def GetMVP(t1,t2):
    p1 = t1.GetMVP()
    p1 = t2.GetMVP()
    if t1.mvpScore > t2.mvpScore:
        return t1.mvp
    elif t2.mvpScore > t1.mvpScore:
        return t2.mvp
    else:
        return (t1.mvp," and",t2.mvp)

def PrintMVP(t1,t2):
    GetMVP(t1,t2)

    # print("RealMVP: ",max(GamePlayerRankings, key=lambda x: x[1]))
    if t1.mvpScore > t2.mvpScore:
        plyr = t1.GetPlayer(t1.mvpId)
        print("Player of the Game:",t1.name,t1.mvp,"On",(champions.loc[champions['Id']==plyr.ChampionPickID]).iloc[0].loc["Name"])
    elif t2.mvpScore > t1.mvpScore:
        plyr = t2.GetPlayer(t2.mvpId)
        print("Player of the Game:",t2.name,t2.mvp,"On",(champions.loc[champions['Id']==plyr.ChampionPickID]).iloc[0].loc["Name"])
    else:
        print("No") 


def GetWinner(t1,t2):
    if t1.GetTotalGold() > t2.GetTotalGold():
        return t1
    if t1.GetTotalGold() < t2.GetTotalGold():
        return t2
    else:
        #coin flip winner if equal gold
        return t1 if rand.randint(0,1) == 1 else t2

def PrintWinner(t1,t2):
    victor = GetWinner(t1,t2)
    print(victor.name,"Has Won the Match")

"""probability functions"""

#function that takes two teams and an integer(maximum number of dragons) then randomly distributes the number of dragons taken by each team based on team stats
def RollDragons(t1,t2,maxdragons):
    print("Rolling Dragons")
    totaldrags = rand.randint(0,maxdragons)
    print("totaldrags: ",totaldrags)
    """future implementation would include a probability distribution based on team stats such as vision control, objective control, and gold leads"""

    if totaldrags == 0:
        return
    
    t1objcontrol = t1.GetTeamObjectiveControl()
    t2objcontrol = t2.GetTeamObjectiveControl()
    t1objprob = t1objcontrol / (t1objcontrol + t2objcontrol)
    t2objprob = t2objcontrol / (t1objcontrol + t2objcontrol)
    t1drags = 0
    t2drags = 0
    t1soulclaimed = False
    t2soulclaimed = False

    elementalsremaining = ElementalDrakePool - totaldrags - t1.dragsTaken - t2.dragsTaken


    print("Objective Control:",t1objcontrol,"|",t2objcontrol)

    #loop through the number of dragons taken and randomly distribute the number of dragons taken by each team
    for i in range(0,totaldrags):
        team1drag = np.random.choice([True,False], 1, p=[t1objprob,t2objprob])[0]
        if team1drag:
            print(t1.name,"has slain the dragon")
            # print(t1.name,"current dragons taken:",t1.dragsTaken)
            # print("Dragon Soul:",t1.dragonSoul)
            t1drags += 1
            t1.dragsTaken += 1
            if t1.dragsTaken == 4 and t2.dragonSoul == False:
                t1.dragonSoul = True
                t1soulclaimed = True
                print("Dragon Soul has been claimed by",t1.name)
            elif t1.dragonSoul or t2.dragonSoul:
                print("Elder Dragon has claimed by",t1.name)
        else:
            print(t2.name,"has slain the dragon")
            # print(t2.name,"current dragons taken:",t2.dragsTaken)
            # print("Dragon Soul:",t2.dragonSoul)
            t2drags += 1
            t2.dragsTaken += 1
            if t2.dragsTaken == 4 and t1.dragonSoul == False:
                t2.dragonSoul = True
                t2soulclaimed = True
                print("Dragon Soul has been claimed by",t2.name)
            elif t1.dragonSoul or t2.dragonSoul:
                print("Elder Dragon has claimed by",t2.name)
        

    # t1.dragsTaken += t1drags
    # t2.dragsTaken += t2drags

    #buff all player lane scores based on the number of dragons taken
    for p in t1.roster:
        p.laneScore += p.laneScore * (t1drags / 10) if t1.dragonSoul == False else p.laneScore * 1.5
        if t1soulclaimed:
            champ = ChampionObjects[p.ChampionPickID]
            champ.Gold += 1000
    for p in t2.roster:
        p.laneScore += p.laneScore * (t2drags / 10) if t2.dragonSoul == False else p.laneScore * 1.5
        if t2soulclaimed:
            champ = ChampionObjects[p.ChampionPickID]
            champ.Gold += 1000

def RollBarons(t1,t2,maxbarons):
    # print("Rolling Barons")
    """future implementation would include a probability distribution based on team stats such as vision control, objective control, and gold leads"""
    totalbarons = rand.randint(0,maxbarons)
    if totalbarons == 0:
        return
    
    t1objcontrol = t1.GetTeamObjectiveControl()
    t2objcontrol = t2.GetTeamObjectiveControl()
    t1objprob = t1objcontrol / (t1objcontrol + t2objcontrol)
    t2objprob = t2objcontrol / (t1objcontrol + t2objcontrol)

    firstbaron = rand.randint(0,1)
    for i in range(0,totalbarons):
        team1baron = np.random.choice([True,False], 1, p=[t1objprob,t2objprob])[0]
        if team1baron:
            t1.baronsTaken += 1
            t1.powerPlay = True
            #allocate random baron powerplay. gold and towers
            #gold gained
            RollTowers(t1,t2,3)
            #structures taken
            RollDragons(t1,t2,1)
            t1.powerPlay = False
        else:
            t2.baronsTaken += 1
            t2.powerPlay = True
            #allocate random baron powerplay. gold and towers
            #gold gained
            RollTowers(t1,t2,3)
            #structures taken
            RollDragons(t1,t2,1)
            t2.powerPlay = False


def RollHeralds(t1,t2,maxheralds):
    # print("Rolling Herald")
    """future implementation would include a probability distribution based on team stats such as vision control, objective control, and gold leads"""
    totalheralds = rand.randint(0,maxheralds)
    firstherald = rand.randint(0,1)

    t1heralds = rand.randint(0,totalheralds)
    t2heralds = totalheralds - t1heralds
    
    if firstherald:
        t1heralds,t2heralds = t2heralds,t1heralds

    t1.heraldsTaken = t1heralds
    t2.heraldsTaken = t2heralds

#function takes in two teams and a number of towers to be taken and randomly distributes the number of towers taken by each team based on team stats
def RollTowers(t1,t2,maxtowers):
    # print("Rolling Towers")
    if maxtowers == 0:
        return
    
    #build probabilities for towers based on maxtowers with with the probability being lower for higher numbers of towers taken but never 0 or 1
    towerprob = []
    for i in range(1,maxtowers):
        towerprob.append(1/(i+1))

    totaltowers = np.random.choice(maxtowers, 1, towerprob)[0]

    t1objcontrol = t1.GetTeamObjectiveControl() if t1.powerPlay == False else t1.GetTeamObjectiveControl() + 50
    t2objcontrol = t2.GetTeamObjectiveControl() if t2.powerPlay == False else t2.GetTeamObjectiveControl() + 50
    t1objprob = t1objcontrol / (t1objcontrol + t2objcontrol)
    t2objprob = t2objcontrol / (t1objcontrol + t2objcontrol)
    t1towerstaken = 0
    t2towerstaken = 0

    """future implementation would include a probability distribution based on team stats such as game time(more likely the later the game is), objective control, and gold leads"""
    
    firsttower = rand.randint(0,1)
    print("Total Towers:",totaltowers)
    for i in range(0,totaltowers):
        team1tower = np.random.choice([True,False], 1, p=[t1objprob,t2objprob])[0]
        #roll a number between 1 and 5 to determine number of champions that will take the tower
        towercredit = rand.randint(1,5)
        #roll between numbers 0,3,4(top,mid,bot) to determine which champion gets buffed
        lanecredit = rand.choice([0,2,3])
        lanechamp = ChampionObjects[t1.roster[lanecredit].ChampionPickID] if team1tower else ChampionObjects[t2.roster[lanecredit].ChampionPickID]
        lanechamp.Gold += 250
        
        if team1tower:
            t1towerstaken += 1
            #allocate bonus gold across team champs if team is behind in gold by more than 2000. 
            if t1.GetTotalGold() < t2.GetTotalGold() - 2000:
                print("Gold Deficit:",t2.GetTotalGold() - t1.GetTotalGold())
                print("Allocating Gold Bounty to",t1.name)
                for p in t1.roster:
                    champ = ChampionObjects[p.ChampionPickID]
                    champ.Gold += 250
                    p.laneScore += 600
        else:
            t2towerstaken += 1
            #allocate bonus gold across team champs if team is behind in gold by more than 2000.
            if t2.GetTotalGold() < t1.GetTotalGold() - 2000:
                print("Gold Deficit:",t1.GetTotalGold() - t2.GetTotalGold())
                print("Allocating Gold Bounty to",t2.name)
                for p in t2.roster:
                    champ = ChampionObjects[p.ChampionPickID]
                    champ.Gold += 250
                    p.laneScore += 600

    t1.towersTaken += t1towerstaken
    t2.towersTaken += t2towerstaken
    t1.towersRemaining -= t2towerstaken
    t2.towersRemaining -= t1towerstaken


#function takes in a list of probabilities and returns a random number based on the input passed in as a list of tuples. The first element of the tuple is the value and the second element is the probability of that value being selected
def RollCustomProbablity(probabilites,probabity_space):
    # print("Rolling Custom Probability")
    # print(probabilites,probabity_space)
    probability_hat = []
    for i in range(0,len(probabilites)):
        # print("DEBUG RollCustomProbability>>",i)
        for j in range(0,int(probabilites[i][1])):
            probability_hat.append(probabilites[i][0])
    
    # print(probability_hat)
    return rand.choice(probability_hat)

"""*************************************"""



"""**********MAIN RUN**********"""

# to replace values from TeamRoster.csv. 1st value is team id, 2nd-6th values are player ids for each lane(top,jg,mid,bot,sup)
team1 = MyTeam(1,1,2,3,4,5)
team2 = MyTeam(2,12,7,11,9,10)

print("set champion stats")

print("Draft in Progress")
print("\n---Ban Phase 1---")
Ban(team1,1)
Ban(team2,2)
Ban(team1,3)
Ban(team2,4)
Ban(team1,5)
Ban(team2,6)
print("\n---Pick Phase 1---\n")
Pick(T1Picks,68)
Pick(T2Picks,109)
Pick(T2Picks,113)
Pick(T1Picks,132)
Pick(T1Picks,119)
Pick(T2Picks,83)
print("\n---Ban Phase 2---")
Ban(team1,7)
Ban(team2,8)
Ban(team1,9)
Ban(team2,10)
print("\n---Pick Phase 2---\n")
Pick(T2Picks,48)
Pick(T1Picks,125)
Pick(T1Picks,143)
Pick(T2Picks,67)

team1.SetPicks(T1Picks)
team2.SetPicks(T2Picks)

print("\n---Swaps in Progress---\n")

team1.SetTeamComps(T1Picks)
team1.PrintComp()



team2.SetTeamComps(T2Picks)
team2.PrintComp()

print("\n---Draft Complete---\n")
print("::::Team 1 Composition Win Rate:", team1.GetCompositionWinRate(), '| Damage Profile:', team1.GetCompositionDamageProfile())
print("::::Team 2 Composition Win Rate:", team2.GetCompositionWinRate(), '| Damage Profile:', team2.GetCompositionDamageProfile())

print("\n---Game Start---\n")

"""Calculate all lane scores for team 1 and team 2"""
"""team1.SetChampionPicks(119,132,67,125,143)"""

#start of lane phase
team1.CalculateTeamLaneScores()
team2.CalculateTeamLaneScores()

"""Calculate Lane Scores"""
goldDiffList = CalculateLaneCSDiffsAll(team1,team2)
print("Gold Diffs",goldDiffList)

"""alocate golddiffs to each player that won their lane"""
# SetEarlyGameChampStates(team1,team2,goldDiffList)
CalculateLaneGaps(team1,team2)
SimulateEarlyGame(team1,team2,goldDiffList)

"""Output lane phase results"""
OutputLaneResults(team1,team2,goldDiffList)
#end of lane phase

PrintGameStats(team1,team2)

#start of midgame phase
"""Simulate Midgame Phase"""
UpdateCS(team1,team2,25)
SimulateMidGame(team1,team2,goldDiffList)
#end of midgame phase

PrintGameStats(team1,team2)

#start of lategame phase
#end of lategame phase

# PrintTeamStats(team1,team2)
PrintWinner(team1,team2)
PrintMVP(team1,team2)
team1.OutputTeamGameRankings()
team2.OutputTeamGameRankings()

print("\n---Game End---\n")
"""END"""