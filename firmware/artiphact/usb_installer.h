#pragma once
/*
  When ARTIPHACT_USB_INSTALLER is defined and the board uses TinyUSB
  (USB Mode = USB-OTG / TinyUSB, not Hardware CDC), the panel also
  appears as a small USB drive named ARTIPHACT with SETUP.BAT on it.

  Flash with FQBN USBMode suitable for TinyUSB on XIAO_ESP32S3_Plus.
*/

#if defined(ARTIPHACT_USB_INSTALLER)

#include "USB.h"
#include "USBMSC.h"
#include "msc_disk.h"

static USBMSC ArtiphactMsc;

static int32_t artiphactMscRead(uint32_t lba, uint32_t offset, void *buffer, uint32_t bufsize) {
  const uint32_t addr = lba * ARTIPHACT_MSC_SECTOR_SIZE + offset;
  if (addr + bufsize > ARTIPHACT_MSC_BYTES) return -1;
  memcpy_P(buffer, ARTIPHACT_MSC_DISK + addr, bufsize);
  return bufsize;
}

static bool artiphactMscStart() {
  USB.productName("Artiphact");
  USB.manufacturerName("Artiphact");
  ArtiphactMsc.vendorID("ARTIPH");
  ArtiphactMsc.productID("SETUP");
  ArtiphactMsc.productRevision("1.0");
  ArtiphactMsc.onRead(artiphactMscRead);
  ArtiphactMsc.mediaPresent(true);
  ArtiphactMsc.begin(ARTIPHACT_MSC_SECTORS, ARTIPHACT_MSC_SECTOR_SIZE);
  USB.begin();
  return true;
}

#else

static bool artiphactMscStart() { return false; }

#endif
