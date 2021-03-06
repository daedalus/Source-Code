import re
import volatility.obj as obj
import volatility.plugins.filescan as filescan
import volatility.win32.modules as modules
import volatility.win32.tasks as tasks
import volatility.utils as utils
import volatility.plugins.malware.malfind as malfind
import volatility.plugins.overlays.windows.windows as windows
from collections import defaultdict
import volatility.conf as conf
import cPickle as pickle


#--------------------------------------------------------------------------------
# constants
#--------------------------------------------------------------------------------

MAJOR_FUNCTIONS = [
    'IRP_MJ_CREATE',
    'IRP_MJ_CREATE_NAMED_PIPE',
    'IRP_MJ_CLOSE',
    'IRP_MJ_READ',
    'IRP_MJ_WRITE',
    'IRP_MJ_QUERY_INFORMATION',
    'IRP_MJ_SET_INFORMATION',
    'IRP_MJ_QUERY_EA',
    'IRP_MJ_SET_EA',
    'IRP_MJ_FLUSH_BUFFERS',
    'IRP_MJ_QUERY_VOLUME_INFORMATION',
    'IRP_MJ_SET_VOLUME_INFORMATION',
    'IRP_MJ_DIRECTORY_CONTROL',
    'IRP_MJ_FILE_SYSTEM_CONTROL',
    'IRP_MJ_DEVICE_CONTROL',
    'IRP_MJ_INTERNAL_DEVICE_CONTROL',
    'IRP_MJ_SHUTDOWN',
    'IRP_MJ_LOCK_CONTROL',
    'IRP_MJ_CLEANUP',
    'IRP_MJ_CREATE_MAILSLOT',
    'IRP_MJ_QUERY_SECURITY',
    'IRP_MJ_SET_SECURITY',
    'IRP_MJ_POWER',
    'IRP_MJ_SYSTEM_CONTROL',
    'IRP_MJ_DEVICE_CHANGE',
    'IRP_MJ_QUERY_QUOTA',
    'IRP_MJ_SET_QUOTA',
    'IRP_MJ_PNP'
]

DEVICE_CODES = {
    0x00000027 : 'FILE_DEVICE_8042_PORT',
    0x00000032 : 'FILE_DEVICE_ACPI',
    0x00000029 : 'FILE_DEVICE_BATTERY',
    0x00000001 : 'FILE_DEVICE_BEEP',
    0x0000002a : 'FILE_DEVICE_BUS_EXTENDER',
    0x00000002 : 'FILE_DEVICE_CD_ROM',
    0x00000003 : 'FILE_DEVICE_CD_ROM_FILE_SYSTEM',
    0x00000030 : 'FILE_DEVICE_CHANGER',
    0x00000004 : 'FILE_DEVICE_CONTROLLER',
    0x00000005 : 'FILE_DEVICE_DATALINK',
    0x00000006 : 'FILE_DEVICE_DFS',
    0x00000035 : 'FILE_DEVICE_DFS_FILE_SYSTEM',
    0x00000036 : 'FILE_DEVICE_DFS_VOLUME',
    0x00000007 : 'FILE_DEVICE_DISK',
    0x00000008 : 'FILE_DEVICE_DISK_FILE_SYSTEM',
    0x00000033 : 'FILE_DEVICE_DVD',
    0x00000009 : 'FILE_DEVICE_FILE_SYSTEM',
    0x0000003a : 'FILE_DEVICE_FIPS',
    0x00000034 : 'FILE_DEVICE_FULLSCREEN_VIDEO',
    0x0000000a : 'FILE_DEVICE_INPORT_PORT',
    0x0000000b : 'FILE_DEVICE_KEYBOARD',
    0x0000002f : 'FILE_DEVICE_KS',
    0x00000039 : 'FILE_DEVICE_KSEC',
    0x0000000c : 'FILE_DEVICE_MAILSLOT',
    0x0000002d : 'FILE_DEVICE_MASS_STORAGE',
    0x0000000d : 'FILE_DEVICE_MIDI_IN',
    0x0000000e : 'FILE_DEVICE_MIDI_OUT',
    0x0000002b : 'FILE_DEVICE_MODEM',
    0x0000000f : 'FILE_DEVICE_MOUSE',
    0x00000010 : 'FILE_DEVICE_MULTI_UNC_PROVIDER',
    0x00000011 : 'FILE_DEVICE_NAMED_PIPE',
    0x00000012 : 'FILE_DEVICE_NETWORK',
    0x00000013 : 'FILE_DEVICE_NETWORK_BROWSER',
    0x00000014 : 'FILE_DEVICE_NETWORK_FILE_SYSTEM',
    0x00000028 : 'FILE_DEVICE_NETWORK_REDIRECTOR',
    0x00000015 : 'FILE_DEVICE_NULL',
    0x00000016 : 'FILE_DEVICE_PARALLEL_PORT',
    0x00000017 : 'FILE_DEVICE_PHYSICAL_NETCARD',
    0x00000018 : 'FILE_DEVICE_PRINTER',
    0x00000019 : 'FILE_DEVICE_SCANNER',
    0x0000001c : 'FILE_DEVICE_SCREEN',
    0x00000037 : 'FILE_DEVICE_SERENUM',
    0x0000001a : 'FILE_DEVICE_SERIAL_MOUSE_PORT',
    0x0000001b : 'FILE_DEVICE_SERIAL_PORT',
    0x00000031 : 'FILE_DEVICE_SMARTCARD',
    0x0000002e : 'FILE_DEVICE_SMB',
    0x0000001d : 'FILE_DEVICE_SOUND',
    0x0000001e : 'FILE_DEVICE_STREAMS',
    0x0000001f : 'FILE_DEVICE_TAPE',
    0x00000020 : 'FILE_DEVICE_TAPE_FILE_SYSTEM',
    0x00000038 : 'FILE_DEVICE_TERMSRV',
    0x00000021 : 'FILE_DEVICE_TRANSPORT',
    0x00000022 : 'FILE_DEVICE_UNKNOWN',
    0x0000002c : 'FILE_DEVICE_VDM',
    0x00000023 : 'FILE_DEVICE_VIDEO',
    0x00000024 : 'FILE_DEVICE_VIRTUAL_DISK',
    0x00000025 : 'FILE_DEVICE_WAVE_IN',
    0x00000026 : 'FILE_DEVICE_WAVE_OUT',
}


class drivercheck(filescan.DriverScan):
    "Driver IRP data extraction for cross-compare"
    "This code is based in the DriverIRP class in devicetree.py"
    "Copyright (C) 2007-2013 Volatility Foundation"
    "Copyright (c) 2010, 2011, 2012 Michael Ligh <michael.ligh@mnin.org>"

    def __init__(self, config, *args, **kwargs):
        filescan.DriverScan.__init__(self, config, *args, **kwargs)
        
        config.add_option("REGEX", short_option = 'r', type = 'str',
                          action = 'store',
                          help = 'Analyze drivers matching REGEX')

    def render_text(self, outfd, data):
        
        
        outfd.write("\n")
        outfd.write("------- driver IRP check -------- \n\n")
        

        addr_space = utils.load_as(self._config)

        # Compile the regular expression for filtering by driver name 
        if self._config.regex != None:
            mod_re = re.compile(self._config.regex, re.I)
        else:
            mod_re = None

        mods = dict((addr_space.address_mask(mod.DllBase), mod) for mod in modules.lsmod(addr_space))
        mod_addrs = sorted(mods.keys())

        bits = addr_space.profile.metadata.get('memory_model', '32bit')

        self.table_header(None, [('i', ">4"),
                                 ('Funcs', "36"),
                                 ('addr', '[addrpad]'),
                                 ('name', '')
                                 ])
       
       
        drivers = dict()
        numberOfDrivers = 0
        for driver in data:
            
            header = driver.get_object_header()

            driver_name = str(header.NameInfo.Name or '')
            # Continue if a regex was supplied and it doesn't match 
            if mod_re != None:
                if not (mod_re.search(driver_name) or
                        mod_re.search(driver_name)): continue

            # Write the standard header for each driver object 
            #outfd.write("{0}\n".format("-" * 50))
            #outfd.write("DriverName: {0}\n".format(driver_name))
            #outfd.write("DriverStart: {0:#x}\n".format(driver.DriverStart))
            #outfd.write("DriverSize: {0:#x}\n".format(driver.DriverSize))
            #outfd.write("DriverStartIo: {0:#x}\n".format(driver.DriverStartIo))

            #print driver_name
            numberOfDrivers += 1
            drivers[driver_name] = {}
        
            #functions = []

            # Write the address and owner of each IRP function 
            for ii, function in enumerate(driver.MajorFunction):
                functions = []
                function = driver.MajorFunction[ii]
                module = tasks.find_module(mods, mod_addrs, addr_space.address_mask(function))
                if module:
                    module_name = str(module.BaseDllName or '')
                else:
                    module_name = "Unknown"
                
                # This is where we check for inline hooks once the 
                # ApiHooks plugin is ported to 2.1. 
                #self.table_row(outfd, i, MAJOR_FUNCTIONS[i], fnction, module_name)
                
                currentFunction = MAJOR_FUNCTIONS[ii]
                currentFunctionNr = ii
                #print "1337 - " + str(ii) + " - " + str(currentFunction)
                data = addr_space.zread(function, 64)
                #outfd.write("\n".join(
                #    ["{0:#x} {1:<16} {2}".format(o, h, i)
                #    for o, i, h in malfind.Disassemble(data = data, 
                #        start = function, bits = bits, stoponret = True)
                #]))
                nameFunction = currentFunction
                
                #outfd.write("instruksjon \n")
                #for o, i, h in malfind.Disassemble(data = data, start = function, bits = bits, stoponret = True):
                    
                    #outfd.write(i + "\n")
                    #if "0x" in str(i):
                    #    i = "--"
                    #i = re.sub('([0x])\w+', '0x000', i)    
                    #instructions.append(i)
                functions.append(module_name)
                    
                drivers[driver_name][str(currentFunctionNr) + " - " + str(nameFunction)] = functions
                #outfd.write("instruksjon slutt \n")
                #functions[str(str(currentFunctionNr) + " - "+ currentFunction)].append(instructions)
                #print functions.keys()
            #drivers[driver_name].append(functions)
            
        outfd.write("# of drivers collected: " + str(numberOfDrivers) +"\n\n" )
        
        locationString = str(conf.ConfObject.opts["location"]).rsplit('/',1)[1] + "_DriverList"
        outfd.write("Storing DriverList as \"" + locationString + "\"\n")
        #print drivers
        with open(locationString + '.p', 'wb') as fp:
            pickle.dump(drivers, fp)
                
                
            