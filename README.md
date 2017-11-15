# About

Inspired by some DIY projects, this script allows you to quickly discern weather conditions by
changing the colors of LEDs to reflect the current METAR information.  You will need a Raspberry
Pi, some WS281X LEDs, and the four letter designators of the airports you are interested in.

This code assumes you've connected to GPIO 18 (PWM0) and have added `blacklist snd_bcm2835` to the
`/etc/modprobe.d/snd-blacklist.conf` file.

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
