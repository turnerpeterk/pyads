import time
import select
import socket
import struct
import threading
from amspacket import AmsPacket
from commands import *

class AdsClient:
    
    def __init__(self, adsConnection):
        self.AdsConnection = adsConnection
        pass
    
    
    AdsConnection = None    
    
    AdsPortDefault = 0xBF02    
    
    AdsChunkSizeDefault = 1024    
    
    Socket = None
    
    _CurrentInvokeID = 0x8000
    
    _CurrentPacket = None
    
    
    @property
    def IsConnected(self):
        return self.Socket != None
    
    
    def Close(self):
        if (self.Socket != None):
            self.Socket.close()
            self.Socket = None
    
    
    
    def Connect(self):
        self.Close()
        self.Socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.Socket.settimeout(3)
        self.Socket.connect((self.AdsConnection.TargetIP, self.AdsPortDefault))
        
        self._BeginAsyncRead()        
        
    
    
    def _BeginAsyncRead(self):
        self._AsyncReadThread = threading.Thread(target=self._AsyncRead)
        self._AsyncReadThread.start()
        
        
    def _AsyncRead(self):
        while (self.IsConnected):
            ready = select.select([self.Socket], [], [], 0.1)
            if (ready[0]):
                try:
                    newPacket = self.ReadAmsPacketFromSocket()
                    if (newPacket.InvokeID == self._CurrentInvokeID):
                        self._CurrentPacket = newPacket
                    else:
                        print("Packet dropped:")
                        print(newPacket)
                except socket.error:
                    self.Close()
                    break
                            
        
    
    def ReadAmsPacketFromSocket(self):        
        
        # read default buffer
        response = self.Socket.recv(self.AdsChunkSizeDefault)
        
        # ensure correct beckhoff tcp header
        if(len(response) < 6):
            return None
        
        # first two bits must be 0
        if (response[0:2] != '\x00\x00'):
            return None
        
        # read whole data length
        dataLen = struct.unpack('I', response[2:6])[0] + 6
        
        # read rest of data, if any
        while (len(response) < dataLen):
            nextReadLen = min(self.AdsChunkSizeDefault, dataLen - len(response))
            response += self.Socket.recv(nextReadLen)

        # cut off tcp-header and return response amspacket
        return AmsPacket.FromBinaryData(response[6:])
        
        
    def GetTcpHeader(self, amsData):
        # pack 2 bytes (reserved) and 4 bytes (length)
        # format _must_ be little endian!
        return struct.pack('<HI', 0, len(amsData))  
    
    
    def SendAndRecv(self, amspacket):        
        if (self.Socket == None):
            self.Connect()
        
        # prepare packet with invoke id 
        self.PrepareCommandInvoke(amspacket)

        # send tcp-header and ams-data
        self.Socket.send(self.GetTCPPacket(amspacket))
        
        # here's your packet
        return self.AwaitCommandInvoke()
    
    
    
    def GetTCPPacket(self, amspacket):
        
        # get ams-data and generate tcp-header
        amsData = amspacket.GetBinaryData()
        tcpHeader = self.GetTcpHeader(amsData)
        
        return tcpHeader + amsData
    
    
    
    def PrepareCommandInvoke(self, amspacket):        
        if(self._CurrentInvokeID < 0xFFFF):
            self._CurrentInvokeID += 1
        else:
            self._CurrentInvokeID = 0x8000
            
        self._CurrentPacket = None
        amspacket.InvokeID = self._CurrentInvokeID
        
        
        
    def AwaitCommandInvoke(self):
        # unfortunately threading.event is slower than this oldschool poll :-(
        timeout = 0
        while (self._CurrentPacket == None):
            timeout += 0.001
            time.sleep(0.001)
            if (timeout > 3):
                raise Exception("Timout: could not receive ADS Answer!")
        
        return self._CurrentPacket                    
        

    

    def ReadDeviceInfo(self):
        return DeviceInfoCommand().Execute(self)


    def Read(self, indexGroup, indexOffset, length):
        return ReadCommand(indexGroup, indexOffset, length).Execute(self)

    
    def Write(self, indexGroup, indexOffset, data):
        return WriteCommand(indexGroup, indexOffset, data).Execute(self)

    
    def ReadState(self):
        return ReadStateCommand().Execute(self)
    
    
    def WriteControl(self, adsState, deviceState, data = ''):
        return WriteControlCommand(adsState, deviceState, data).Execute(self)


    def AddDeviceNotification(self):
        raise NotImplementedError()
    
    
    def DeleteDeviceNotification(self):
        raise NotImplementedError()


    def ReadWrite(self, indexGroup, indexOffset, readLen, dataToWrite = ''):
        return ReadWriteCommand(indexGroup, indexOffset, readLen, dataToWrite).Execute(self)
        