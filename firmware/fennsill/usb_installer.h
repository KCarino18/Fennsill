#pragma once
/*
  When FENNSILL_USB_INSTALLER is defined and the board uses TinyUSB
  (USB Mode = USB-OTG / TinyUSB, not Hardware CDC), the panel also
  appears as a small USB drive named FENNSILL with SETUP.BAT on it.

  Flash with FQBN USBMode suitable for TinyUSB on XIAO_ESP32S3_Plus.
*/

#if defined(FENNSILL_USB_INSTALLER)

#include "USB.h"
#include "USBMSC.h"
#include "msc_disk.h"

static USBMSC FennsillMsc;

static int32_t fennsillMscRead(uint32_t lba, uint32_t offset, void *buffer, uint32_t bufsize) {
  const uint32_t addr = lba * FENNSILL_MSC_SECTOR_SIZE + offset;
  if (addr + bufsize > FENNSILL_MSC_BYTES) return -1;
  memcpy_P(buffer, FENNSILL_MSC_DISK + addr, bufsize);
  return bufsize;
}

static bool fennsillMscStart() {
  USB.productName("Fennsill");
  USB.manufacturerName("Fennsill");
  FennsillMsc.vendorID("ARTIPH");
  FennsillMsc.productID("SETUP");
  FennsillMsc.productRevision("1.0");
  FennsillMsc.onRead(fennsillMscRead);
  FennsillMsc.mediaPresent(true);
  FennsillMsc.begin(FENNSILL_MSC_SECTORS, FENNSILL_MSC_SECTOR_SIZE);
  USB.begin();
  return true;
}

#else

static bool fennsillMscStart() { return false; }

#endif
