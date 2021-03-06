#       Copyright (C) 2013
#       Written on behalf of Flirc
#       by Sean Poyser (seanpoyser@gmail.com)
#

import utils
import ctypes

NO_WAIT = 0
WAIT    = 1

BOOTLOADER = 1
FIRMWARE   = 2

DFU_ATTTEMPTS = 2

EOK               = 0
STATE_PLAYBACK    = 0
STATE_RECORD      = 1
STATE_DELETE      = 2
FUNK_SUCCESS      = 3
ERR_NO_SPACE      = 4  # Can't Record, no space
ERR_BUTTON_EXISTS = 5  # Can't Record, button exists
ERR_KEY_NOT_FOUND = 6  # Can't Delete, button not found
NO_INTERRUPT      = 4  # Returned from setRecord
ENOMEM            = 5  # Out of memory
EBADF             = 6  # Bad File Descriptor
EFAULT            = 7  # Bad Address
EINVAL            = 8  # Invalid argument
ENODEV            = 9  # No Device
ENOSYS            = 10 # Function not implemented
ECANCELED         = 11 # Operation Canceled
EWRONGDEV         = 12 # Wrong Device
EIDXRANGE         = 13 # Index Out Of Range
ENXIO             = 14 # No such device or address
LIBUSBERR         = 15 # self.libUSB Error Code
ETIMEOUT          = 16 # Error, time out
_ERROR_T_COUNT    = 17 # 

VID          = 0x20A0
MANUFACTURER = ctypes.c_char_p('flirc.tv') 


def callback(perc, dp):
    ctypes.cast(dp, ctypes.py_object).value.update(int(perc))
    return 0


class Flirc(object):
    def __init__(self):
        self.cancelRecord = False
        self.cancelErase  = False
        self.response     = EOK

        self.version = 0

        self.dfuLeaveAttempts  = 0
        self.fwUpgradeAttempts = 0

        self.interrupt = None

        self.connected = False
        self.lib       = None
        self.loadLibrary()


    def loadLibrary(self):
        path = 'unknown'
        try:
            path     = utils.getFlircLibrary()
            self.lib = ctypes.cdll.LoadLibrary(path) 
        except Exception, e:
            utils.log('***** loadLibary Failed *****')
            utils.log('library path = %s' % path)
            utils.log('err = %s' % str(e))
            self.lib = None
            utils.ok(1, 5, 0, 6)


    def __del__(self):
        if not self.lib:
            return 
        self.lib.fl_close_device()        


    def cancelRecording(self):
        self.cancelRecord = True


    def cancelErasing(self):
        self.cancelErase = True


    def checkConnect(self):
        if not self.lib:
            return False

        if self.connected:
            response = self.lib.fl_eeprom_peek(0)
            if response < 0:
                self.lib.fl_close_device()
 		self.version   = 0
                self.connected = False
            
            return self.connected  

        response     = self.lib.fl_open_device(VID, MANUFACTURER)
        self.version = 0

        if response == FIRMWARE:
            utils.log('OPEN Response = FIRMWARE')
            self.version = self.getVersionStr()
            utils.log('Firmware version %s detected' % self.version)
            self.connected = True
            return self.connected

        elif response == BOOTLOADER:
            utils.log('OPEN Response = BOOTLOADER')

            if self.dfuLeaveAttempts < DFU_ATTTEMPTS:
                self.dfuLeaveAttempts += 1
                utils.log('Leaving bootloader, attempt %d' % self.dfuLeaveAttempts)
                self.lib.fl_leave_bootloader()
        
            elif self.fwUpgradeAttempts == 0:
                self.fwUpgradeAttempts += 1
                utils.log('Attempting to restore original firmware')
                self.doUpgradeFW(utils.getRestoreFW())

            else:   
                utils.log('Stuck in Bootloader, email support@flirc.tv') 

            self.lib.fl_close_device()        
            
        else:
            utils.log('OPEN Response = %s' % str(response))

        return self.connected


    def getVersionStr(self):        
        try:
            func = self.lib.fl_version_str
            func.restype = ctypes.c_char_p
            return func().split(' ')[0]
        except:
            return '0'


    def getVersion(self):        
        try:
            func = self.lib.fl_version
            func.restype = ctypes.c_float
            return func()
        except:
            return 0


    def getErrorText(self, code):
        if not self.checkConnect():
            return ''

        func = self.lib.strerr
        func.restype = ctypes.c_char_p
        return func(code)


    def checkResponse(self, response):
        if response == -ETIMEOUT:
            return utils.TIMED_OUT
        
        if response == -ENODEV:
            return utils.NO_FLIRC

        if response == -LIBUSBERR:
            return utils.NO_FLIRC

        if response == -ERR_BUTTON_EXISTS:
            return utils.BUTTON_EXISTS

        if response == -ERR_KEY_NOT_FOUND:
            return utils.ERASE_NOT_FOUND

        if response == -EFAULT:
            return utils.TRANSFER_ERROR

        if response == -EINVAL:
            return utils.INVALID

        if not self.checkConnect():
            return utils.NO_LIBRARY


        return utils.FLIRC_OK

 
    def format(self):
        if not self.checkConnect():
            return utils.NO_FLIRC

        response = self.lib.fl_format_config()
        utils.log('FORMAT Response = %d' % response)
        if (response == 0):
            return utils.FORMATTED

        return utils.NO_FLIRC


    def setNormal(self):
        if not self.checkConnect():
            return False
        self.lib.fl_set_normal()
        return True


    def clearState(self):
        if not self.checkConnect():
            return False
        self.lib.fl_clear_state()
        return True


    def close(self):
        if not self.lib:
            return

        if not self.connected:
            return

        self.lib.fl_close_device()
        self.connected = False


    def upgradeFW(self, filename):
        if not self.checkConnect():
            return utils.NO_FLIRC

        self.close()

        return self.doUpgradeFW(filename)


    def doUpgradeFW(self, filename):
        utils.log('doupgradeFW %s' % filename)        

        dp = utils.progress(1, 0, 11)
        
        FUNC     = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p))      
        theFunc  = FUNC(callback)
        theFile  = ctypes.c_char_p(filename) 
        theDP    = ctypes.c_void_p(id(dp))
        response = self.lib.fl_upgrade_fw(theFile, VID, MANUFACTURER, ctypes.cast(theDP, ctypes.POINTER(ctypes.c_void_p)), theFunc)

        dp.close()

        utils.log('UPGRADE_FW Response = %d' % response)

        check = self.checkResponse(response)
        if check != utils.FLIRC_OK:
            #UPGRADE_FAILED
            return check        

        return utils.UPGRADE_OK

        
    def loadConfig(self, filename):
        if not self.checkConnect():
            return utils.NO_FLIRC

        utils.log('loadConfig %s' % filename)

        theFilename = ctypes.c_char_p(filename) 
        response    = self.lib.fl_load_config(theFilename)
        
        utils.log('LOADCONFIG Response = %d' % response)

        check = self.checkResponse(response)
        if check != utils.FLIRC_OK:
            return check

        return utils.LOAD_OK


    def saveConfig(self, filename):
        if not self.checkConnect():
            return utils.NO_FLIRC

        utils.log('saveConfig %s' % filename)

        theFilename = ctypes.c_char_p(filename) 
        response    = self.lib.fl_save_config(theFilename)
        
        utils.log('SAVECONFIG Response = %d' % response)

        check = self.checkResponse(response)
        if check != utils.FLIRC_OK:
            return check

        return utils.SAVE_OK
        

    def erase(self):
        if not self.checkConnect():
            return utils.NO_FLIRC

        self.cancelErase = False
        
        response = self.lib.fl_set_delete(WAIT)

        utils.log('ERASE Response = %d' % response)

        if self.cancelErase:
            return utils.ERASE_CANCELED

        check = self.checkResponse(response)
        if check != utils.FLIRC_OK:
            return check

        return utils.ERASE_OK
   

    def recordKey(self, key):
        if not self.checkConnect():
            return utils.NO_FLIRC

        self.cancelRecord = False

        key = key.lower()

        #is it a F[1-12] key?
        if key[0] == 'f' and len(key) > 1:
            key = int(key[1:])
            if key >= 1 and key <=12:
                key = 'F%d' % key  

        if 'hid' in key:
            key      = int(key[3:])
            theKey   = ctypes.c_int(key) 
            response = self.lib.fl_set_record_api(0, theKey, WAIT)
        else:            
            theKey   = ctypes.c_char_p(key) 
            response = self.lib.fl_set_record(theKey, WAIT)
        
        utils.log('RECORDKEY Response = %d' % response)

        if self.cancelRecord:
            return utils.RECORD_CANCELED
      
        check = self.checkResponse(response)
        if check != utils.FLIRC_OK:
            return check        

        return utils.RECORD_OK