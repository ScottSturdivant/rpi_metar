# About

Inspired by some DIY projects, this script allows you to quickly discern weather conditions by
changing the colors of LEDs to reflect the current METAR information.  You will need a Raspberry
Pi, some WS281X LEDs, and the four letter designators of the airports you are interested in.

This code assumes you've connected to GPIO 18 (PWM0) and have added `blacklist snd_bcm2835` to the
`/etc/modprobe.d/snd-blacklist.conf` file.

Don't want to DIY it? This is the code that powers the
[Aviation Weather Maps](https://aviationweathermaps.com) products. Enjoy a premade product, or
continue reading and happy tinkering!

# Install

```
sudo su
apt install python3-venv python3-dev
python3 -m venv /opt/rpi_metar
source /opt/rpi_metar/bin/activate
pip install wheel
pip install rpi_metar
```

# Configuration

You need to tell `rpi_metar` which LEDs correspond to which airports.  You may do this by
creating the `/etc/rpi_metar.conf` file.  There must be an `[airports]` section where the airport
codes are assigned to LEDs.  For example:

```
[airports]
KDEN = 0
KBOS = 1
```

The LED indexes can be skipped and do not need to be continuous.  If you don't have an LED
associated with an airport, it does not need to be entered.

Airports may also be repeated at different indexes, though to enable this the keys must be unique:

```
# this displays KDEN at both 3 and 45
[airports]
KDEN1 = 3
KDEN2 = 45
```

The behavior of the program can be tweaked by including a `settings` section in the configuration
file. These configuration values can be set:

| Option             | Default | Description                                                     |
|--------------------|---------|-----------------------------------------------------------------|
| brightness         | 128     | An integer (from 0 to 255) controlling the intensity of the LEDs appear. In a well lit room, 75 or 85 are recommended. In a bright room, try 128. |
| disable_gamma      | False   | A boolean that will allow you to disable the gamma correction. You may need this if using LEDs from different manufacturers / batches in a single run. |
| do_fade            | True    | A boolean controlling whether or not stations will fade into their new color during a transition. If `False`, they will just abruptly change colors. |
| lightning          | True    | A boolean that controls if thunderstorm conditions should be visually indicated. They will appear as short blinks of white before going back to the station's original color. |
| lightning_duration | 1.0     | A float controlling how long a station blinks white before returning to its original color. |
| max_wind           | 30      | An integer that sets the threshold for max wind speed in knots. Any steady or gusting winds above this value will result in yellow blinking lights. |
| metar_refresh_rate | 300     | An integer that controls how frequently (in seconds) the METAR information is polled. |
| sources            | NOAA,NOAABackup,SkyVector | The data sources to be used. A comma separated list of class names from the sources.py file. `BOM` is another source for Australian stations. `IFIS` is a source for New Zealand stations that requires further configuration.|
| wind               | True    | A boolean that controls if high wind speeds should be visually indicated. They will appear as short blinks of yellow before going back to the station's original color. |
| wind_duration      | 1.0     | A float controlling how long a station blinks yellow before returning to its original color. |
| unknown_off        | True    | A boolean that controls whether or not stations that are not reporting data will just turn off. If set to `False`, after three attempts (during which time they appear as yellow), they will instead turn to orange. |

For example, to reduce the brightness of the LEDs:

```
[settings]
brightness = 85
```

Another feature includes setting up a legend.  These are a series of lights that will always
display their assigned static color.  Similar to setting up the airports by LED index, you can
assign flight categories to LED indexes:

```
[legend]
VFR = 10
IFR = 11
LIFR = 12
MVFR = 13
WIND = 14
LIGHTNING = 15
UNKNOWN = 16
OFF = 17
MISSING = 18
```

For the `IFIS` data source, credentials are required for logging into the service. They may be provided thusly:

```
[ifis]
username = your_username
password = your_password
```

The colors of the LEDs themselves along with their association to flight categories / behaviors can also be
modified. To adjust individual colors, a 3-int tuple can be provided in GRB format:

```
[colors]
GREEN = (250, 0, 0) # Overriding a default color value.
NAVY_BLUE = (22, 22, 22) # A new value, not overriding a default.
```

Then, if you wanted to associate these new color definitions to behaviors, you can do the following:

```
[flight_categories]
LIFR = NAVY_BLUE # LIFR will now show as (22, 22, 22)
IFR = (66, 66, 66) # You can also just provide a new 3-int tuple without having given it a name.
```

Though not explicitly listed in that `flight_categories` section, since VFR defaults to GREEN, it will
now be displayed using our modified `(250, 0, 0)` parameters.

# Autostart

Create the `/etc/systemd/system/rpi_metar.service` file with the following contents:

```
[Unit]
Description=METAR Display
Wants=network-online.target
After=network.target network-online.target

[Service]
ExecStart=/opt/rpi_metar/bin/rpi_metar
User=root
Group=root
Restart=always

[Install]
WantedBy=multi-user.target
```

Make systemd aware of the changes:

```
systemctl daemon-reload
```

Make sure it's set to run at boot:

```
systemctl enable rpi_metar
```

Start the service:

```
systemctl start rpi_metar
```
