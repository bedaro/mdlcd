# mdlcd
LCDproc client for monitoring /proc/mdstat information on RAID arrays

Requires Python 3 (tested on 3.8 but should work on earlier versions), mdstat,
and pylcddc. The included service file requires systemd.

# Installing

For a system install, use '''pip install --system -r requirements.txt''' to
install dependencies to the system, copy the script to /usr/local/bin, and copy
the service to /etc/systemd/user. Make a symlink to it in /etc/systemd/system,
then run '''systemd start mdlcd''' and '''systemd enable mdlcd'''. The service
is configured to run as the user nobody, since no privileges are required.

# Usage

Customization is possible through command arguments.

    usage: mdlcd.py [-h] [--host LCDD_HOST] [-p LCDD_PORT] [-n POLLFREQ]
                    [-a MDARRAYS] [--mdstat-file STATFILE] [--version]

    LCDproc client for monitoring /proc/mdstat information on RAID arrays

    optional arguments:
      -h, --help            show this help message and exit
      --host LCDD_HOST      LCDd host
      -p LCDD_PORT, --port LCDD_PORT
                            LCDDd port
      -n POLLFREQ, --poll POLLFREQ
                            Polling interval for mdstat
      -a MDARRAYS, --array MDARRAYS
                            Monitor the given device (defaults to all devices)
      --mdstat-file STATFILE
                            /proc/mdstat file to monitor (for testing or remote
                            monitoring)
      --version             show program's version number and exit
