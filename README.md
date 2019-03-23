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
apt install python3-venv
python3 -m venv /opt/rpi_metar
source /opt/rpi_metar/bin/activate
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
| metar_refresh_rate | 5       | An integer that controls how frequently (in minutes) the METAR information is polled. |
| papertrail         | True    | A boolean controlling if logs are sent to a centralized system. Only METAR information and processing results are logged. |
| wind               | True    | A boolean that controls if high wind speeds should be visually indicated. They will appear as short blinks of yellow before going back to the station's original color. |
| wind_duration      | 1.0     | A float controlling how long a station blinks yellow before returning to its original color. |
| unknown_off        | True    | A boolean that controls whether or not stations that are not reporting data will just turn off. If set to `False`, after three attempts (during which time they appear as yellow), they will instead turn to orange. |

For example, to reduce the brightness of the LEDs:

```
[settings]
brightness = 85
```

# Autostart

Create the `/etc/systemd/system/rpi_metar.service` file with the following contents:

```
[Unit]
Description=METAR Display

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
