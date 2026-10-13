#!/usr/bin/env bash
# Create the dev VM "jellyfin-epgs-dev" on Leetop (192.168.0.216, libvirt, bridge br0).
#   tools/dev/create_vm.sh     (run on omarchy; needs ssh media1@192.168.0.216 + sudo there)
# Ubuntu 26.04 cloud image, 6 GB / 4 vCPU / 80 GB, user media1 with this machine's ssh key and
# passwordless sudo. Refuses if the VM already exists. Never touches Leetop's other VMs.
set -euo pipefail
HOST=media1@192.168.0.216
DIR=/var/lib/libvirt/images/jellyfin-epgs
VM=jellyfin-epgs-dev
IMG_URL=https://cloud-images.ubuntu.com/releases/26.04/release/ubuntu-26.04-server-cloudimg-amd64.img
pubkey=$(cat ~/.ssh/id_rsa.pub)

ssh "$HOST" "sudo virsh -c qemu:///system dominfo $VM" >/dev/null 2>&1 && { echo "$VM already exists" >&2; exit 1; }

ssh "$HOST" "set -e
  sudo mkdir -p $DIR
  [ -f $DIR/base.img ] || sudo curl -fsSL -o $DIR/base.img $IMG_URL
  sudo cp $DIR/base.img $DIR/$VM.qcow2
  sudo qemu-img resize -q $DIR/$VM.qcow2 80G
  t=\$(mktemp -d)
  cat > \$t/meta-data <<EOF
instance-id: $VM
local-hostname: $VM
EOF
  cat > \$t/user-data <<EOF
#cloud-config
users:
  - name: media1
    groups: [sudo]
    shell: /bin/bash
    sudo: 'ALL=(ALL) NOPASSWD:ALL'
    ssh_authorized_keys: ['$pubkey']
timezone: Asia/Tokyo
package_update: true
packages: [qemu-guest-agent]
runcmd:
  - systemctl enable --now qemu-guest-agent
EOF
  sudo xorriso -as mkisofs -quiet -J -r -V CIDATA -o $DIR/$VM-seed.iso \$t/user-data \$t/meta-data 2>/dev/null
  rm -rf \$t
  sudo virt-install --connect qemu:///system --name $VM --memory 6144 --vcpus 4 --cpu host-passthrough \
    --osinfo ubuntu24.04 --import \
    --disk path=$DIR/$VM.qcow2,format=qcow2,bus=virtio --disk path=$DIR/$VM-seed.iso,device=cdrom \
    --network bridge=br0,model=virtio --channel unix,target.type=virtio,target.name=org.qemu.guest_agent.0 \
    --graphics none --noautoconsole --autostart
  sudo virsh -c qemu:///system domiflist $VM"
