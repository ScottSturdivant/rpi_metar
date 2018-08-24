import logging

from crontab import CronTab

log = logging.getLogger(__name__)


def set_upgrade_schedule():
    """Makes sure the code tries to update itself periodically."""
    cron = CronTab(user='root')

    cmd = '/opt/rpi_metar/bin/upgrade.sh'
    changes_made = False

    # The code should check daily, and at every reboot
    daily_found = False
    reboot_found = False

    # Search for daily and reboot checks, removing anything else
    for job in cron.find_command(cmd):
        freq = job.frequency()
        if freq == 365:
            daily_found = True
        elif freq == 525600:
            reboot_found = True
        else:
            cron.remove(job)
            changes_made = True

    if not daily_found:
        job = cron.new(command=cmd)
        job.every(1).days()
        changes_made = True
        log.info('Adding daily update to cron.')
    if not reboot_found:
        job = cron.new(command=cmd)
        job.every_reboot()
        changes_made = True
        log.info('Adding reboot update to cron.')

    if changes_made:
        cron.write()
        log.info('Updated crontab.')
