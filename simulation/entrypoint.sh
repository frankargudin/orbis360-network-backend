#!/bin/bash
set -e

DEVICE_NAME=${DEVICE_NAME:-"sim-device"}
DEVICE_TYPE=${DEVICE_TYPE:-"switch"}

echo "══════════════════════════════════════════"
echo "  Orbis360 Simulated Device: $DEVICE_NAME"
echo "  Type: $DEVICE_TYPE"
echo "  SSH: port 22 (root/admin123)"
echo "  SNMP: port 161 (community: public)"
echo "══════════════════════════════════════════"

# Set sysName for SNMP
echo "sysname $DEVICE_NAME" >> /etc/snmp/snmpd.conf
echo "sysdescr Orbis360 Simulated $DEVICE_TYPE - $DEVICE_NAME" >> /etc/snmp/snmpd.conf

# Start SNMP daemon
snmpd -f -Lo -C -c /etc/snmp/snmpd.conf &

# Start SSH daemon in foreground
/usr/sbin/sshd -D -e
