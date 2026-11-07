"""Constants for Salus iT600 Plus."""

DOMAIN = "salus_plus"
CONF_EUID = "euid"
CONF_AUX_DEVICES = "aux_devices"  # {uid: {"model", "name"}} WC/receiver ever seen
AUX_IMPORT_MODELS = ("it600Receiver", "it600WC")
DEFAULT_SCAN_INTERVAL = 30
# After a write the thermostat needs a few seconds; B11 settles in ~10 s.
REFRESH_DELAYS = (6, 12)

# sIT600TH HoldType values
HOLD_SCHEDULE = 0
HOLD_TEMPORARY = 1
HOLD_PERMANENT = 2
HOLD_AWAY = 6
HOLD_STANDBY = 7

# sIT600TH SystemMode values
SYSTEM_MODE_COOL = 3
SYSTEM_MODE_HEAT = 4
