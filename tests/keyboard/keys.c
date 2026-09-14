// Test-only virtual keyboard with a standard evdev keymap, unlike wtype's dynamic map.
#define _GNU_SOURCE
#include <wayland-client.h>
#include <xkbcommon/xkbcommon.h>
#include <sys/mman.h>
#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "virtual-keyboard.h"
static struct wl_seat *seat;
static struct zwp_virtual_keyboard_manager_v1 *manager;
static void global(void *data, struct wl_registry *registry, uint32_t id, const char *name, uint32_t version) {
    if (!strcmp(name, "wl_seat")) seat = wl_registry_bind(registry, id, &wl_seat_interface, 1);
    if (!strcmp(name, "zwp_virtual_keyboard_manager_v1")) manager = wl_registry_bind(registry, id, &zwp_virtual_keyboard_manager_v1_interface, 1);
}
static void removed(void *data, struct wl_registry *registry, uint32_t id) {}
int main(int argc, char **argv) {
    struct wl_display *display = wl_display_connect(NULL);
    if (!display) return 1;
    struct wl_registry *registry = wl_display_get_registry(display);
    const struct wl_registry_listener listener = { global, removed };
    wl_registry_add_listener(registry, &listener, NULL);
    wl_display_roundtrip(display);
    if (!seat || !manager) return 2;
    struct xkb_context *context = xkb_context_new(XKB_CONTEXT_NO_FLAGS);
    struct xkb_rule_names names = { .layout = "us" };
    struct xkb_keymap *map = xkb_keymap_new_from_names(context, &names, XKB_KEYMAP_COMPILE_NO_FLAGS);
    struct xkb_state *state = xkb_state_new(map);
    char *keymap = xkb_keymap_get_as_string(map, XKB_KEYMAP_FORMAT_TEXT_V1);
    size_t length = strlen(keymap) + 1;
    int fd = memfd_create("skipper-test-keymap", 0);
    if (fd < 0 || write(fd, keymap, length) != length) return 3;
    struct zwp_virtual_keyboard_v1 *keyboard = zwp_virtual_keyboard_manager_v1_create_virtual_keyboard(manager, seat);
    zwp_virtual_keyboard_v1_keymap(keyboard, WL_KEYBOARD_KEYMAP_FORMAT_XKB_V1, fd, length);
    wl_display_roundtrip(display);
    close(fd);
    free(keymap);
    for (int i = 1; i < argc; i++) {
        int value = atoi(argv[i] + 1);
        if (argv[i][0] == 's') { usleep(value * 1000); continue; }
        int down = argv[i][0] == 'd';
        struct timespec now;
        clock_gettime(CLOCK_MONOTONIC, &now);
        zwp_virtual_keyboard_v1_key(keyboard, now.tv_sec * 1000 + now.tv_nsec / 1000000, value, down);
        xkb_state_update_key(state, value + 8, down ? XKB_KEY_DOWN : XKB_KEY_UP);
        zwp_virtual_keyboard_v1_modifiers(keyboard,
            xkb_state_serialize_mods(state, XKB_STATE_MODS_DEPRESSED),
            xkb_state_serialize_mods(state, XKB_STATE_MODS_LATCHED),
            xkb_state_serialize_mods(state, XKB_STATE_MODS_LOCKED),
            xkb_state_serialize_layout(state, XKB_STATE_LAYOUT_EFFECTIVE));
        wl_display_roundtrip(display);
    }
    zwp_virtual_keyboard_v1_destroy(keyboard);
    wl_display_roundtrip(display);
    wl_display_disconnect(display);
    xkb_state_unref(state);
    xkb_keymap_unref(map);
    xkb_context_unref(context);
    return 0;
}
