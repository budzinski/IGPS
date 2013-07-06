'''
Created on 03-05-2013

@author: Olek
'''
from DataAccessModule import NodeDb as NDB
from DataAccessModule import HomeNodeDb as HNDB
from ConfigurationModule import Configuration as C
from CommunicationModule import BeaconCommunicationModule as BCM
from CommunicationModule import NodeCommunicationReceivingModule as NCRM
from CommunicationModule import NodeCommunicationSendingModule as NCSM
from Common import NodeStatesEnumerator as NSE
from CalculationModule.CalculateSubMatrixModule import CalculateSubMatrixController as CSMCM
from CalculationModule.NodePositionProviderModule import NodePositionProvider as NPP

import logging
from CommunicationModule.NodeCommunicationSendingModule import NodeCommunicationSendingModule

class NodeController():

    def __init__(self, nodeId):
        self.launched = False
        self.nodeId = nodeId
        
        # Data Access Module
        self.nodeDb = NDB.NodeDb()
        self.homeNodeDb = HNDB.HomeNodeDb()
        
        # Communication Module
        self.beaconReceiver = BCM.BeaconCommunicationModule()
        self.beaconReceiver.onBeaconSignalReceive += self._BeaconSignalReceived
        
        self.nodeReceiver = NCRM.NodeCommunicationReceivingModule(self.nodeId)
        self.nodeReceiver.onSignalReceivedAtForeignNode += self._SignalReceivedAtForeignNode
        self.nodeReceiver.onAskedForCalculateSubMatrix += self._AskedForCalculateSubMatrix
        self.nodeReceiver.onEndOfPreparingPartialResultByForeignNode += self._RegisterReadyNodeToDownloadFromSubMatrix
        self.nodeReceiver.onRequestToSendPartialResult += self._SendCalculatedSubMatrix
        self.nodeReceiver.onPartialResult += self._AddPartialResult
        self.nodeReceiver.onSubMatrixSendingEnd += self._ReceivedSubMatrixSendingEnd
        self.nodeReceiver.onReceivingAskOfNodePosition += self._AskedForNodePosition
        self.nodeReceiver.onReceivingNodePosition += self._ReceivedNodePosition
        
        # Calculation Module
        self.calculationModule = CSMCM.CalculateSubMatrixController()
        self.nodePositionProvider = NPP.NodePositionProvider()
        
        # Downloading queue manager
        self.isCurrentlyComputing = False
        
        logging.debug("Node created: " + str(self.nodeId))
        
    def StartNode(self):
        if False == self.launched:
            self.beaconReceiver.Start()
            self.nodeReceiver.Start()
            self.launched = True
        else:
            raise Exception("Already launched")
        logging.info("Node Started: " + str(self.nodeId))
    
    def StopNode(self):
        self.launched = False
        self.beaconReceiver.Stop()
        self.nodeReceiver.Stop()
    
    #===========================================================================
    # Events requested by Beacon receiver
    #===========================================================================
    def _BeaconSignalReceived(self, messageHeader, receivingTime):
        self.nodeDb.RegisterNewBeaconMessage(messageHeader, receivingTime, self.nodePositionProvider.GetCurrentPosition())
        sender = NCSM.NodeCommunicationSendingModule(sourceNodeId = self.nodeId, messageHeader = messageHeader)
        sender.InformHomeAboutNewBeaconSignalReceive(messageHeader.homeNodeId)
    
    #===========================================================================
    # Methods for distributed computations
    #===========================================================================
    def _SignalReceivedAtForeignNode(self, dataFromOtherNode):
        self.homeNodeDb.RegisterNewSignalReceivedAtNode(messageHeader = dataFromOtherNode.messageHeader, 
                                                        nodeId = dataFromOtherNode.sendingNodeId)
        nodesForMessage = self.homeNodeDb.GetNodesListForSpecificBeaconMessageIdentity(messageHeader = dataFromOtherNode.messageHeader)
        if len(nodesForMessage) >= C.Configuration.minNumberToStartMatrixCreation:
            nodesToAsk = self.homeNodeDb.GetNodesListForSpecificBeaconMessageIdentity(messageHeader = dataFromOtherNode.messageHeader,
                                                                                      inState = NSE.NodeStatesEnumerator.NEWRECEIVED)
            for node in nodesToAsk:
                self._AskNodeForCalculateSubMatrix(messageHeader = dataFromOtherNode.messageHeader, nodeId = node)
    
    def _AskNodeForCalculateSubMatrix(self, messageHeader, nodeId):
        sender = NodeCommunicationSendingModule(sourceNodeId = self.nodeId, messageHeader = messageHeader)
        sender.AskNodeToPrepareSubMatrix(destinationNodeId = nodeId)
        self.homeNodeDb.ChangeStateOfNodeForSpecificBeaconMessageIdentity(messageHeader = messageHeader,
                                                                          nodeId = nodeId,
                                                                          newState = NSE.NodeStatesEnumerator.ASKED)
    
    def _AskedForCalculateSubMatrix(self, dataFromOtherNode):
        record = self.nodeDb.GetRecordForMessageHeader(messageHeader = dataFromOtherNode.messageHeader)
        subMatrix = self.calculationModule.CalculateSubMatrix(record = record)
        self.nodeDb.AddSubMatrixToRecord(recordToUpdate = record, subMatrix = subMatrix)
        self._InformHomeThatSubMatrixWasCalculated(messageHeader = dataFromOtherNode.messageHeader, nodeId = dataFromOtherNode.messageHeader.homeNodeId)
    
    def _InformHomeThatSubMatrixWasCalculated(self, messageHeader, nodeId):
        sender = NodeCommunicationSendingModule(sourceNodeId = self.nodeId, messageHeader = messageHeader)
        sender.InformHomeThatSubMatrixWasCreated(destinationNodeId = nodeId)
    
    def _RegisterReadyNodeToDownloadFromSubMatrix(self, dataFromOtherNode):
        self.homeNodeDb.ChangeStateOfNodeForSpecificBeaconMessageIdentity(messageHeader = dataFromOtherNode.messageHeader,
                                                                          nodeId = dataFromOtherNode.sendingNodeId,
                                                                          newState = NSE.NodeStatesEnumerator.DONE)
        if False == self.isCurrentlyComputing:
            self.isCurrentlyComputing = True
            self._AskNodeToTransmitSubMatrix(messageHeader = dataFromOtherNode.messageHeader, nodeId = dataFromOtherNode.sendingNodeId)
    
    def _AskNodeToTransmitSubMatrix(self, messageHeader, nodeId):
        sender = NodeCommunicationSendingModule(sourceNodeId = self.nodeId, messageHeader = messageHeader)
        sender.RequestNodeToStartSubMatrixTransfer(destinationNodeId = nodeId)
        self.homeNodeDb.ChangeStateOfNodeForSpecificBeaconMessageIdentity(messageHeader = messageHeader,
                                                                          nodeId = nodeId,
                                                                          newState = NSE.NodeStatesEnumerator.WHANT)
    
    def _SendCalculatedSubMatrix(self, dataFromOtherNode):
        record = self.nodeDb.GetRecordForMessageHeader(messageHeader = dataFromOtherNode.messageHeader)
        sender = NodeCommunicationSendingModule(sourceNodeId = self.nodeId, messageHeader = dataFromOtherNode.messageHeader)
        sender.SendSubMatrixToNode(destinationNodeId = dataFromOtherNode.sendingNodeId, subMatrix = record.subMatrix)
    
    def _AddPartialResult(self, dataFromOtherNode):
        self.homeNodeDb.AddValueToSubMatrixCell(messageHeader = dataFromOtherNode.messageHeader,
                                                nodeId        = dataFromOtherNode.sendingNodeId,
                                                x             = dataFromOtherNode.subMatrixX,
                                                y             = dataFromOtherNode.subMatrixY,
                                                z             = dataFromOtherNode.subMatrixZ,
                                                value         = dataFromOtherNode.subMatrixValue)
    
    def _ReceivedSubMatrixSendingEnd(self, dataFromOtherNode):
        print "End at:", self.nodeId
        self.homeNodeDb.ChangeStateOfNodeForSpecificBeaconMessageIdentity(messageHeader = dataFromOtherNode.messageHeader,
                                                                          nodeId        = dataFromOtherNode.sendingNodeId,
                                                                          newState      = NSE.NodeStatesEnumerator.END)
        
        sender = NodeCommunicationSendingModule(sourceNodeId = self.nodeId, messageHeader = dataFromOtherNode.messageHeader)
        sender.AskNodeToSendItsPosition(destinationNodeId = dataFromOtherNode.sendingNodeId)
        self.homeNodeDb.ChangeStateOfNodeForSpecificBeaconMessageIdentity(messageHeader = dataFromOtherNode.messageHeader,
                                                                          nodeId        = dataFromOtherNode.sendingNodeId,
                                                                          newState      = NSE.NodeStatesEnumerator.POSASKED)
    
    def _AskedForNodePosition(self, dataFromOtherNode):
        record = self.nodeDb.GetRecordForMessageHeader(messageHeader = dataFromOtherNode.messageHeader)
        sender = NodeCommunicationSendingModule(sourceNodeId = self.nodeId, messageHeader = dataFromOtherNode.messageHeader)
        sender.SendSelfPositionToNode(destinationNodeId  = dataFromOtherNode.sendingNodeId, otherNodePosition = record.nodePosition)
    
    def _ReceivedNodePosition(self, dataFromOtherNode):
        print "Position at:", self.nodeId
        self.homeNodeDb.SetReceivingNodePosition(messageHeader = dataFromOtherNode.messageHeader,
                                                 nodeId        = dataFromOtherNode.sendingNodeId,
                                                 position      = dataFromOtherNode.otherNodePosition)
        
        self._AddSubMatrixToBeaconPositionMatrix(dataFromOtherNode = dataFromOtherNode)
        self.homeNodeDb.ChangeStateOfNodeForSpecificBeaconMessageIdentity(messageHeader = dataFromOtherNode.messageHeader,
                                                                          nodeId        = dataFromOtherNode.sendingNodeId,
                                                                          newState      = NSE.NodeStatesEnumerator.NOLONGERNEEDED)
        self._ReceiveMissingSubMatrices(dataFromOtherNode.messageHeader)
        
    def _AddSubMatrixToBeaconPositionMatrix(self, dataFromOtherNode):
        oldMatrix = self.homeNodeDb.GetBeaconPositionMatrix(messageHeader = dataFromOtherNode.messageHeader)
        record = self.homeNodeDb.GetRecordForMessageHeaderAndNodeId(messageHeader = dataFromOtherNode.messageHeader,
                                                                    nodeId = dataFromOtherNode.sendingNodeId)
        for xLocal in range(len(record.calculatedSubMatrix.data)):
            for yLocal in range(len(record.calculatedSubMatrix.data[xLocal])):
                # TODO: Add 3D
                if record.calculatedSubMatrix.data[xLocal][yLocal] != 0:
                    oldMatrix.data[record.receivingNodePosition.X + xLocal][record.receivingNodePosition.Y + yLocal] += \
                    record.calculatedSubMatrix.data[xLocal][yLocal]
        self.homeNodeDb.UpdateBeaconPositionMatrix(messageHeader = dataFromOtherNode.messageHeader, matrix = oldMatrix)
        self.isCurrentlyComputing = False
    
    def _ReceiveMissingSubMatrices(self, messageHeader):
        nodesToAsk = self.homeNodeDb.GetNodesListForSpecificBeaconMessageIdentity(messageHeader = messageHeader, inState = NSE.NodeStatesEnumerator.DONE)
        if (len(nodesToAsk) >= 1):
            self.isCurrentlyComputing = True
            self._AskNodeToTransmitSubMatrix(messageHeader = messageHeader, nodeId = nodesToAsk[0])
            self.homeNodeDb.ChangeStateOfNodeForSpecificBeaconMessageIdentity(messageHeader = messageHeader,
                                                                              nodeId        = nodesToAsk[0],
                                                                              newState      = NSE.NodeStatesEnumerator.WHANT)
        else:
            logging.critical(self.homeNodeDb.GetBeaconPositionMatrix(messageHeader = messageHeader))
if __name__ == "__main__":
    pass