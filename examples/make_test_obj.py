"""Make a Controller and Remote for the Test device
"""
from lsst.ts import salobj

salobj.set_random_lsst_dds_partition_prefix()
salinfo = salobj.SalInfo("Test", 1)
command_names = salinfo.command_names
event_names = salinfo.event_names
telemetry_names = salinfo.telemetry_names
print(f"commands for {salinfo.name}:")
for item in command_names:
    print(f"  {item}")
print(f"\nevents for {salinfo.name}:")
for item in event_names:
    print(f"  {item}")
print(f"\ntelemetry topics for {salinfo.name}:")
for item in telemetry_names:
    print(f"  {item}")

print("\nmake remote")
remote = salobj.Remote("Test", 1)
print("make controller")
controller = salobj.Controller("Test", 1)

print("\ndata fields for arrays")
print([item for item in dir(remote.cmd_setArrays.data) if not item.startswith("_")])

print("\ndata fields for scalars")
print([item for item in dir(remote.cmd_setScalars.data) if not item.startswith("_")])
