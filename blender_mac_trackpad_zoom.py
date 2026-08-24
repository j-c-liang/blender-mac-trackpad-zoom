# SPDX-FileCopyrightText: 2026 jc-liang
# SPDX-License-Identifier: GPL-3.0-or-later
# Provided without warranty. Users are responsible for determining whether
# this add-on is suitable for their needs and assume all risks from its use.

bl_info = {
    "name": "Mac Trackpad Pinch Zoom Speed",
    "author": "jc-liang",
    "version": (2, 0, 0),
    "blender": (5, 2, 0),
    "location": "Preferences > Add-ons",
    "description": "Fix inconsistent macOS trackpad pinch zoom sensitivity and adjust its speed",
    "category": "3D View",
}

import math
import bpy

from bpy.types import Operator, AddonPreferences
from bpy.props import FloatProperty
from bpy_extras import view3d_utils


addon_keymaps = []


def get_prefs(context):
    addon = context.preferences.addons.get(__name__)

    if addon:
        return addon.preferences

    return None


class VIEW3D_OT_trackpad_zoom_speed(Operator):
    bl_idname = "view3d.trackpad_zoom_speed"
    bl_label = "Trackpad Pinch Zoom Speed"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return (
            context.area is not None
            and context.area.type == 'VIEW_3D'
            and context.region is not None
            and context.region.type == 'WINDOW'
            and context.region_data is not None
        )

    def invoke(self, context, event):

        rv3d = context.region_data

        # Keep Blender's native behavior in Camera View.
        # The add-on handles only regular Perspective and Orthographic views.
        if rv3d.view_perspective == 'CAMERA':
            return {'PASS_THROUGH'}

        # In Blender 5.2 TRACKPADZOOM events, the magnification amount is
        # encoded as mouse_x - mouse_prev_x, even though the physical mouse
        # cursor has not moved horizontally.
        dx = event.mouse_x - event.mouse_prev_x

        if dx == 0:
            return {'FINISHED'}

        prefs = get_prefs(context)

        if prefs:
            speed = prefs.speed
        else:
            speed = 1.0

        # Respect Preferences > Navigation > Invert Zoom Direction.
        if context.preferences.inputs.invert_mouse_zoom:
            dx = -dx

        # ------------------------------------------------------------
        # Calculate zoom sensitivity
        # ------------------------------------------------------------
        #
        # Blender's native Dolly calculation makes sensitivity depend on
        # the cursor's distance from a viewport edge. Consequently, the
        # same pinch gesture zooms at different speeds near the top and
        # bottom of the viewport.
        #
        # This calculation deliberately does not use the actual mouse Y
        # coordinate. At 1.0x, it approximates Blender's native sensitivity
        # when the cursor is near the vertical center of the viewport.

        ui_scale = max(
            float(context.preferences.system.ui_scale),
            0.000001
        )

        viewport_height = max(
            float(context.region.height),
            1.0
        )

        # Local sensitivity of the native Dolly calculation near the
        # vertical center of the viewport.
        base_sensitivity = 2.0 / (
            5.0 * ui_scale * ui_scale
            + viewport_height * 0.5
        )

        exponent = (
            base_sensitivity
            * float(dx)
            * float(speed)
        )

        # Prevent a malformed trackpad event from causing a very large jump.
        exponent = max(
            -1.5,
            min(1.5, exponent)
        )

        # Exponential scaling makes zoom-in and zoom-out symmetric.
        factor = math.exp(exponent)

        old_distance = float(rv3d.view_distance)

        if old_distance <= 0.0:
            return {'PASS_THROUGH'}

        new_distance = old_distance * factor

        # Keep the value within a safe range to avoid floating-point extremes.
        new_distance = max(
            0.0000001,
            min(1.0e12, new_distance)
        )

        # Recalculate the effective factor if the value was clamped above.
        factor = new_distance / old_distance


        # ------------------------------------------------------------
        # Zoom to Mouse Position
        # ------------------------------------------------------------

        if context.preferences.inputs.use_zoom_to_mouse:

            try:
                old_location = rv3d.view_location.copy()

                mouse_coord = (
                    event.mouse_region_x,
                    event.mouse_region_y
                )

                # Project the cursor onto the depth plane of the current
                # view pivot to find the corresponding 3D location.
                point_under_mouse = (
                    view3d_utils.region_2d_to_location_3d(
                        context.region,
                        rv3d,
                        mouse_coord,
                        old_location
                    )
                )

                if point_under_mouse is not None:

                    # Move the view pivot while zooming so that the point
                    # beneath the cursor remains approximately stationary.
                    rv3d.view_location = (
                        old_location
                        + (
                            point_under_mouse
                            - old_location
                        )
                        * (1.0 - factor)
                    )

            except Exception:
                # If projection fails in an unusual viewport state, retain
                # normal center-based zooming instead of cancelling the event.
                pass


        # ------------------------------------------------------------
        # Apply zoom
        # ------------------------------------------------------------

        rv3d.view_distance = new_distance

        context.region.tag_redraw()

        # Consume the TRACKPADZOOM event so Blender's native Dolly operator
        # does not apply a second zoom operation.
        return {'FINISHED'}


class TrackpadZoomPreferences(AddonPreferences):
    bl_idname = __name__

    speed: FloatProperty(
        name="Pinch Zoom Speed",
        description="Trackpad pinch zoom speed multiplier",

        default=1.0,

        min=0.5,
        max=10.0,

        soft_min=0.5,
        soft_max=10.0,

        precision=2,

        # Allow fine adjustments with dragging or arrow controls.
        step=1,
    )

    def draw(self, context):

        layout = self.layout

        layout.prop(
            self,
            "speed",
            text="Pinch Zoom Speed",
            slider=True
        )

        layout.label(
            text=f"Current: {self.speed:.2f}x"
        )

        layout.separator()

        layout.label(
            text="1.0x ≈ native speed near viewport center"
        )

        layout.label(
            text="Pinch sensitivity is independent of cursor Y position"
        )

        layout.label(
            text="Camera View keeps Blender's native zoom"
        )


classes = (
    VIEW3D_OT_trackpad_zoom_speed,
    TrackpadZoomPreferences,
)


def register():

    for cls in classes:
        bpy.utils.register_class(cls)

    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon

    if kc is None:
        return

    km = kc.keymaps.new(
        name='3D View',
        space_type='VIEW_3D',
    )

    # Blender 5.2 event names:
    # C/C++ internal name: MOUSEZOOM
    # Python/RNA name: TRACKPADZOOM
    kmi = km.keymap_items.new(
        VIEW3D_OT_trackpad_zoom_speed.bl_idname,
        type='TRACKPADZOOM',
        value='ANY',
    )

    addon_keymaps.append(
        (km, kmi)
    )


def unregister():

    for km, kmi in addon_keymaps:

        try:
            km.keymap_items.remove(kmi)

        except Exception:
            pass

    addon_keymaps.clear()

    for cls in reversed(classes):

        try:
            bpy.utils.unregister_class(cls)

        except Exception:
            pass


if __name__ == "__main__":
    register()
