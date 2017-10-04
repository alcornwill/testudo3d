# ====================== BEGIN GPL LICENSE BLOCK ======================
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ======================= END GPL LICENSE BLOCK ========================


bl_info = {
    "name": "Testudo3D",
    "author": "Will Alcorn",
    "version": (0, 1),
    "blender": (2, 78, 0),
    "location": "3D View > Tools > T3D",
    "description": "create 3D tilemaps",
    "warning": "",
    "wiki_url": "",
    "category": "3D View",
}

import logging
from os.path import splitext, basename, dirname, join
import bpy
from math import ceil, sqrt, radians, degrees
from bpy.props import (
    StringProperty,
    BoolProperty,
    IntProperty,
    FloatProperty,
    EnumProperty,
    PointerProperty,
    CollectionProperty,
    IntVectorProperty
)
from bpy.types import (
    Panel,
    Operator,
    PropertyGroup,
    Header,
    UIList
)
from mathutils import Vector

from .tilemap3d import init_object_props, update_3dviews, get_first_group_name, get_tileset_from_group, round_vector, roundbase
from .turtle3d import Turtle3D
from .autotiler3d import AutoTiler3D
from .operator import T3DOperatorBase, ManualModeOperator, AutoModeOperator, clamp
from .events import subscribe, unsubscribe, send_event

addon_keymaps = []

def make_linked_duplicate(src):
    obj = src.copy()
    if src.data:
        obj.data = src.data.copy()
    bpy.context.scene.objects.link(obj)
    return obj

def create_group_instance(group_name):
    group = bpy.data.groups[group_name]
    bpy.ops.object.empty_add()
    empty = bpy.context.object
    empty.name = group_name
    empty.empty_draw_size = 0 # don't like everything looking hairy
    empty.dupli_type = 'GROUP'
    empty.dupli_group = group
    return empty

def get_children(obj, children=None):
    # recursive
    if not children:
        children = []
    children += obj.children
    for child in obj.children:
        get_children(child, children)
    return children

class TilesetList(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        if T3DOperatorBase.running_modal and not t3d.manual_mode:
            row.enabled = bool(item.rules)
        row.label(item.tileset)
        # rules = item.tileset.rules
        # row.label("{} | {}".format(item.tileset, rules if rules else "None"))
        sub = row.row()
        sub.scale_x = 2.0
        sub.prop_search(item, 'rules', bpy.data, 'texts', text='')

class TilePropertyGroup(PropertyGroup):
    tile3d = StringProperty(
        name='Tile'
    )

class TilesetPropertyGroup(PropertyGroup):
    tileset = StringProperty( # todo rename 'name'
        name='Tileset',
    )
    tiles = CollectionProperty(
        name='Tiles',
        type=TilePropertyGroup
    )
    rules = StringProperty(name='Rules')
    last_tile = StringProperty()

def enum_previews(self, context):
    return T3DProperties.enum_items

class T3DProperties(PropertyGroup):
    # IT'S WEIRD how the state of t3d has become split between this and the operator
    # however it kind-of makes sense because this data is per-scene
    # and t3d is always singleton
    # and this is gui data structures
    # and t3d is optimized data structures
    # todo ok this is actually terrible
    # you can select a tileset in one scene that doesn't exist in modal scene
    # properties should be on operator, not scene
    # (but operator doesn't exist until executed...)

    tile3d_library_path = StringProperty(
        name="Tile3D Library Path",
        description="Path to your tile3d library .blend file",
        subtype="FILE_PATH"
    )

    brush_size = IntProperty(
        name="Brush Size",
        description='Radius of brush',
        min=1,
        max=8,
        default=1
    )

    outline = BoolProperty(
        name='Outline',
        description='Use outline brush',
        default=False
    )

    def get_cursor_pos(self):
        if T3DOperatorBase.running_modal:
            vec = t3d.cursor.pos.copy()
            round_vector(vec)
            return vec
        return (0,0,0)
    def set_cursor_pos(self, value):
        t3d.cursor.pos = Vector(value)
        t3d.construct_select_cube()

    cursor_pos = IntVectorProperty(
        name='Cursor Pos',
        get=get_cursor_pos,
        set=set_cursor_pos
    )

    tile_previews_ = IntProperty(default=-1)

    def get_tile3d(self):
        return self.tile_previews_

    def set_tile3d(self, value):
        self.tile_previews_ = value
        id, name, desc, icon, i = self.enum_items[value]  # index == i?
        send_event('set_tile3d', id)

    tile_previews = EnumProperty(
        name='Tile',
        items=enum_previews,
        get=get_tile3d,
        set=set_tile3d
    )

    def refresh_tilesets(self):
        tilesets = {tileset.tileset: tileset for tileset in self.tilesets}
        for tileset in self.tilesets:
            tileset.tiles.clear()
        for group in bpy.data.groups:
            try:
                obj = group.objects[group.name]
            except KeyError:
                continue # not a tile
            name = obj.tileset
            if not name: continue # not a tile
            if name not in tilesets:
                tileset = self.tilesets.add()
                tileset.tileset = name
                tilesets[name] = tileset
            else:
                tileset = tilesets[name]
            tile3d = tileset.tiles.add()
            tile3d.tile3d = obj.name

        for i, tileset in enumerate(self.tilesets):
            if not tileset.tiles:
                self.tilesets.remove(i)
        self.tileset_idx = clamp(self.tileset_idx, 0, len(self.tilesets)-1)
        self.refresh_enum_items()
        send_event('refresh_tilesets')

    # having non-blender properties on here is hacky
    enum_items = []
    enum_items_dict = {}
    use_previews = False

    def refresh_enum_items(self):
        T3DProperties.enum_items = []
        tileset = self.tileset
        if not tileset: return
        use_previews = False
        for i, tile3d in enumerate(tileset.tiles):
            obj = bpy.data.objects[tile3d.tile3d]
            use_previews = use_previews or obj.preview.is_image_custom
            icon = obj.preview.icon_id if obj.preview.is_image_custom else ""
            T3DProperties.enum_items.append((obj.name, obj.name, "", icon, i))
        T3DProperties.use_previews = use_previews
        T3DProperties.enum_items_dict = {id: i for id, name, desc, icon, i in T3DProperties.enum_items}

    tilesets = CollectionProperty(
        name='Tilesets',
        description='Tilesets (for auto-tiling)',
        type=TilesetPropertyGroup
    )

    def get_tileset(self):
        if self.tilesets:
            return self.tilesets[self.tileset_idx]
    def set_tileset(self, name):
        for i, tileset in enumerate(self.tilesets):
            if tileset.tileset == name:
                self.tileset_idx = i
                return
    tileset = property(get_tileset, set_tileset)

    tileset_idx_ = IntProperty()
    def get_tileset_idx(self):
        return self.tileset_idx_
    def set_tileset_idx(self, value):
        if T3DOperatorBase.running_modal and not t3d.manual_mode:
            tileset = self.tilesets[value]
            if not tileset.rules:
                # if in auto-mode, don't let set index to tileset that doesn't have rules
                return
        if T3DOperatorBase.running_modal and t3d.manual_mode:
            tileset = self.tileset
            tileset.last_tile = self.tile_previews

        self.tileset_idx_ = value
        self.refresh_enum_items()

        if T3DOperatorBase.running_modal and t3d.manual_mode:
            tileset = self.tileset
            if tileset.last_tile:
                try:
                    self.tile_previews = tileset.last_tile
                except TypeError:
                    tile3d = self.enum_items[0][0]
                    self.tile_previews = tile3d
            else:
                tile3d = self.enum_items[0][0]
                self.tile_previews = tile3d

    tileset_idx = IntProperty(
        default=0,
        get=get_tileset_idx,
        set=set_tileset_idx
    )

    roomgen_name = StringProperty(
        name='Name',
        description='Name of tileset to be generated',
        default='Tileset'
    )

    user_layer_ = IntProperty()

    def get_user_layer(self):
        return self.user_layer_

    def set_user_layer(self, value):
        self.user_layer_ = value
        bpy.context.scene.layers[value] = True

    user_layer = IntProperty(
        name='Layer',
        min=0,
        max=19,
        description='Layer to work in',
        default=0,
        get=get_user_layer,
        set=set_user_layer
    )

    def get_down(self):
        if T3DOperatorBase.running_modal:
            return t3d.state.paint
        return False

    def set_down(self, value):
        if T3DOperatorBase.running_modal:
            t3d.state.paint = value

    down = BoolProperty(
        name='Down',
        default=False,
        get=get_down,
        set=set_down
    )

class TilesetActionsOperator(bpy.types.Operator):
    bl_idname = "view3d.t3d_tileset_actions"
    bl_label = "Tileset Actions"

    action = bpy.props.EnumProperty(
        items=(
            ('UP', "Up", ""),
            ('DOWN', "Down", ""),
            ('REFRESH', "Refresh", "Refresh Tilesets"),
        )
    )

    def invoke(self, context, event):
        prop = context.scene.t3d_prop
        idx = prop.tileset_idx

        try:
            item = prop.tilesets[idx]
        except IndexError:
            pass
        else:
            if self.action == 'DOWN' and idx < len(prop.tilesets) - 1:
                item_next = prop.tilesets[idx+1].name
                prop.tileset_idx += 1
            elif self.action == 'UP' and idx >= 1:
                item_prev = prop.tilesets[idx-1].name
                prop.tileset_idx -= 1
        if self.action == 'REFRESH':
            prop.refresh_tilesets()

        return {"FINISHED"}

class T3DToolsPanel(Panel):
    bl_idname = "view3d.t3d_tools_panel"
    bl_label = "Tools"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'
    bl_category = "T3D"
    bl_context = "objectmode"

    def draw(self, context):
        layout = self.layout
        prop = context.scene.t3d_prop

        layout.operator(ManualModeOperator.bl_idname)
        layout.operator(AutoModeOperator.bl_idname)

        col = layout.column()
        col.enabled = T3DOperatorBase.running_modal and t3d.manual_mode
        if prop.use_previews:
            col.template_icon_view(prop, 'tile_previews')
        col.prop(prop, 'tile_previews') # still have to draw both because previews has no text + sometimes rubbish

        row = layout.row()
        row.template_list('TilesetList', '', prop, 'tilesets', prop, 'tileset_idx', rows=3)

        col = row.column(align=True)
        col.enabled = not T3DOperatorBase.running_modal
        col.operator(TilesetActionsOperator.bl_idname, icon='FILE_REFRESH', text="").action = 'REFRESH'
        col.separator()
        col.operator(TilesetActionsOperator.bl_idname, icon='TRIA_UP', text="").action = 'UP'
        col.operator(TilesetActionsOperator.bl_idname, icon='TRIA_DOWN', text="").action = 'DOWN'

class T3DDrawingPanel(Panel):
    bl_idname = "view3d.t3d_drawing_panel"
    bl_label = "Drawing"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'
    bl_category = "T3D"
    bl_context = "objectmode"

    def draw(self, context):
        layout = self.layout
        prop = context.scene.t3d_prop

        col = layout.column()
        col.enabled = T3DOperatorBase.running_modal
        col.prop(prop, 'user_layer')
        row = col.row()
        row.prop(prop, 'cursor_pos', text='')
        self.display_selected_tile3d(col, context)
        col.operator(SetActiveTile3D.bl_idname)
        col.operator(CursorToSelected.bl_idname)
        col.operator(Goto3DCursor.bl_idname)
        col.prop(prop, 'down')
        col.prop(prop, 'outline')
        col.prop(prop, 'brush_size')

    def display_selected_tile3d(self, layout, context):
        obj = context.object
        text = obj.group if obj else 'None'
        layout.label("selected: {}".format(text))

class T3DUtilsPanel(Panel):
    bl_idname = "view3d.t3d_utils_panel"
    bl_label = "Utils"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'
    bl_category = "T3D"
    bl_context = "objectmode"

    def draw(self, context):
        layout = self.layout
        prop = context.scene.t3d_prop

        row = layout.row(align=True)
        sub = row.row(align=True)
        sub.scale_x = 3.0
        sub.prop(prop, 'tile3d_library_path', text="")
        row.operator(LinkTile3DLibrary.bl_idname)
        layout.operator(T3DSetupTilesOperator.bl_idname)
        layout.separator()
        col = layout.column(align=True)
        col.operator(RoomGenOperator.bl_idname)
        col.prop(prop, 'roomgen_name', text='')
        layout.operator(MakeTilesRealOperator.bl_idname)
        layout.operator(AlignTiles.bl_idname)
        # layout.operator(XmlExportOperator.bl_idname)

class T3DObjectPanel(Panel):
    bl_idname = 'OBJECT_PT_t3d_object_panel'
    bl_label = 'T3D'
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'object'

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        obj = context.object
        row.enabled = self.is_enabled(obj)
        row.prop(context.object, 'tileset')

    def is_enabled(self, obj):
        name = obj.name
        if name not in bpy.data.groups: return False
        group = bpy.data.groups[name]
        if name not in group.objects: return False
        return True

class LinkTile3DLibrary(Operator):
    """Link all groups from linked library"""
    bl_idname = "view3d.link_tile3d_library"
    bl_label = "Link"

    def execute(self, context):
        t3d = context.scene.t3d_prop
        path = t3d.tile3d_library_path
        if not path: return {'FINISHED'}
        with bpy.data.libraries.load(path, link=True) as (data_src, data_dst):
            # link groups
            data_dst.groups = data_src.groups
            self.report({'INFO'}, 'linked {} groups'.format(len(data_src.groups)))
            # link texts
            data_dst.texts = data_src.texts
        return {'FINISHED'}

class SetActiveTile3D(Operator):
    # we need this as operator because modal operator only works for one window
    bl_idname = "view_3d.t3d_set_active_tile3d"
    bl_label = "Set Active Tile3D"

    tile3d = None
    tileset = None

    @classmethod
    def poll(cls, context):
        if not T3DOperatorBase.running_modal: return False
        if not t3d.manual_mode: return False
        obj = context.object
        if not obj: return False

        if obj.is_src_tile:
            tile3d = obj.name
            tileset = obj.tileset
        else:
            tile3d = obj.group
            if not tile3d: return False
            tileset = get_tileset_from_group(tile3d)
            if not tileset: return False
        SetActiveTile3D.tile3d = tile3d
        SetActiveTile3D.tileset = tileset
        return True

    def execute(self, context):
        # todo using t3d.prop seems wrong
        t3d.prop.tileset = self.tileset
        t3d.prop.tile_previews = self.tile3d
        update_3dviews()
        return {'FINISHED'}

class CursorToSelected(Operator):
    bl_idname = "view_3d.t3d_cursor_to_selected"
    bl_label = "Cursor To Selected"

    @classmethod
    def poll(cls, context):
        return T3DOperatorBase.running_modal and context.object

    def execute(self, context):
        t3d.cursor.pos = context.object.pos
        t3d.construct_select_cube()
        return {'FINISHED'}

class Goto3DCursor(Operator):
    bl_idname = "view_3d.t3d_goto_3dcursor"
    bl_label = "Goto 3D Cursor"
    bl_description = "Go to the 3D cursor (draws line if 'down')"

    @classmethod
    def poll(cls, context):
        return T3DOperatorBase.running_modal

    def execute(self, context):
        # note: doesn't make sense when root rotated in x or y
        mat_world = t3d.root.matrix_world
        # todo is it mat * vec?
        pos = (context.space_data.cursor_location - t3d.root.location) * mat_world
        round_vector(pos)
        t3d.line(pos.x, pos.y)
        t3d.construct_select_cube()
        bpy.ops.ed.undo_push()
        return {'FINISHED'}

class AlignTiles(Operator):
    bl_idname = 'view_3d.t3d_align_tiles'
    bl_label = 'Align Tiles'
    bl_description = 'Align tiles to grid'

    @classmethod
    def poll(cls, context):
        return T3DOperatorBase.running_modal

    def execute(self, context):
        # for every child, align to grid
        for child in t3d.root.children:
            vec = child.pos
            round_vector(vec)
            child.pos = vec

            rot = degrees(child.rot)
            rot = roundbase(rot, 90)
            child.rot = radians(rot)
        return {'FINISHED'}

class T3DSetupTilesOperator(Operator):
    bl_idname = 'view3d.t3d_setup_tiles'
    bl_label = 'Setup 3D Tiles'
    bl_description = 'Setup objects in scene as tiles'

    def __init__(self):
        bpy.types.Operator.__init__(self)
        self.objects = None

    @classmethod
    def poll(self, context):
        return context.mode == "OBJECT" and not T3DOperatorBase.running_modal

    def execute(self, context):
        self.setup_tiles(context)
        return {'FINISHED'}

    def create_groups(self):
        for obj in self.objects:
            children = get_children(obj)
            if obj.name in bpy.data.groups:
                # reuse
                group = bpy.data.groups[obj.name]
                for object in list(group.objects):
                    group.objects.unlink(object)
            else:
                group = bpy.data.groups.new(name=obj.name)
            group.objects.link(obj)
            for child in children:
                group.objects.link(child)
            group.dupli_offset = obj.location

    def layout_in_grid(self, border=2):
        dimx = ceil(sqrt(len(self.objects)))
        count = 0
        x = 0
        y = 0
        offset = ((dimx - 1) * border) / 2

        for obj in self.objects:
            obj.location.x = x - offset
            obj.location.y = y - offset
            count += 1
            x += border
            if count >= dimx:
                y += border
                x = 0
                count = 0

    def rename_objects(self):
        for obj in self.objects:
            # if contains whitespace replace with underscore
            if ' ' in obj.name:
                obj.name = obj.name.replace(' ', '_')
            # hmm all tile names across tilesets must be unique?
            # if not obj.name.startswith(tileset):
            #     obj.name = tileset + '_' + obj.name

    def setup_tiles(self, context):
        self.objects = [obj for obj in bpy.context.scene.objects if not obj.parent and not obj.hide]
        self.rename_objects()
        self.layout_in_grid()
        self.create_groups()

class RoomGenOperator(Operator):
    bl_idname = 'view3d.t3d_room_gen'
    bl_label = 'Room Gen'
    bl_description = 'Generate tileset from "Wall", "Floor" and "Ceiling" groups'

    masks = (
        0b0000,
        0b0001,
        0b0011,
        0b0101,
        0b0111,
        0b1111
    )

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and not T3DOperatorBase.running_modal

    def execute(self, context):
        name = context.scene.t3d_prop.roomgen_name
        self.make_tileset(name, 'Wall', 'Ceiling', 'Floor')
        return {'FINISHED'}

    def make_tileset(self, name, wall, ceiling, floor):
        if (wall not in bpy.data.groups or
            ceiling not in bpy.data.groups or
            floor not in bpy.data.groups):
            self.report({'WARNING'}, 'group "Wall", "Floor" or "Ceiling" not found, no tiles generated')
            return

        if name in bpy.data.scenes:
            # reuse
            scene = bpy.data.scenes[name]
            for obj in list(scene.objects):
                scene.objects.unlink(obj)
        else:
            scene = bpy.data.scenes.new(name=name)
        bpy.context.screen.scene = scene

        name = name.lower()

        index = 0
        lines = []
        for j in range(4):
            c = j & 0b01
            f = j & 0b10
            for m in self.masks:
                objs = []
                # walls
                for i in range(4):
                    w = m & 1 << i
                    if not w:
                        obj = create_group_instance(wall)
                        obj.rotation_euler.z = radians(i * -90)
                        objs.append(obj)
                # ceiling
                if not c:
                    obj = create_group_instance(ceiling)
                    objs.append(obj)
                # floor
                if not f:
                    obj = create_group_instance(floor)
                    objs.append(obj)

                # if not objs: continue
                bpy.ops.object.empty_add()
                empty = bpy.context.object
                empty.name = name + format(index, '02d')
                empty.name = name + format(index, '02d') # insist (can't reuse objects
                empty.empty_draw_size = 0
                for obj in objs:
                    obj.parent = empty

                rule = (j << 4) | m
                rulestr = "{} {}\n".format(format(rule, '06b'), empty.name)
                lines.append(rulestr)

                index += 1

        text_name = name+'.txt'
        if text_name in bpy.data.texts:
            # reuse
            text = bpy.data.texts[text_name]
            text.clear()
        else:
            text = bpy.data.texts.new(name=text_name)
        for line in lines:
            text.write(line)

        bpy.ops.view3d.t3d_setup_tiles()
        scene.rules = text_name

class MakeTilesRealOperator(Operator):
    bl_idname = 'view3d.t3d_make_tiles_real'
    bl_label = 'Make Tiles Real'
    bl_description = 'Edit details on selected tile without affecting the rest (destructive)'

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and not T3DOperatorBase.running_modal

    def execute(self, context):
        tiles = [obj for obj in context.selected_objects if obj.dupli_group]
        for tile in tiles:
            pos = tile.location.copy()
            rot = tile.rotation_euler.copy()
            group = tile.dupli_group
            for obj in group.objects:
                if tile.name.startswith(obj.name): continue # ignore root empty
                new = make_linked_duplicate(obj)
                new.parent = None
                new.location = new.location + pos
                new.rotation_euler.rotate(rot)
            bpy.data.objects.remove(tile, do_unlink=True)
        return {'FINISHED'}

class XmlExportOperator(Operator):
    # test
    bl_idname = 'view3d.t3d_xml_export'
    bl_label = 'XML Export'
    bl_description = 'Export scene to custom T3D XML format'

    def execute(self, context):
        import xml.etree.cElementTree as et
        fp = bpy.data.filepath
        if not fp:
            self.report({'ERROR'}, 'Blend not saved, cannot save xml file')
            return {'FINISHED'}
        blenddir = dirname(fp)
        path = join(blenddir, 'tiles.xml')

        # todo
        root = et.Element('Scene')

        tilesets = et.SubElement(root, 'Tilesets')
        tileset1 = et.SubElement(tilesets, 'Tileset1', name='tileset1')
        tile1 = et.SubElement(tileset1, 'Tile', name='tile1')
        tile2 = et.SubElement(tileset1, 'Tile', name='tile2')
        tile3 = et.SubElement(tileset1, 'Tile', name='tile3')
        tileset2 = et.SubElement(tilesets, 'Tileset2', name='tileset2')

        root1 = et.SubElement(root, 'Root', name='Root.001', matrix="1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1")
        tile1 = et.SubElement(root1, 'Tile', name='tile1.001', matrix="1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1", tile='tile1', tileset='tileset1', layer="0")
        tile2 = et.SubElement(root1, 'Tile', name='tile1.002', matrix="1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1", tile='tile1', tileset='tileset1', layer="1")
        tile3 = et.SubElement(root1, 'Tile', name='tile2.001', matrix="1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1", tile='tile2', tileset='tileset1', layer="0")
        root2 = et.SubElement(root1, 'Root', name='Root.002', matrix="1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1")
        root3 = et.SubElement(root, 'Root', name='Root.003', matrix="1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1")

        tree = et.ElementTree(root)
        tree.write(path)

        return {'FINISHED'}

def register():
    bpy.utils.register_module(__name__)
    bpy.types.Scene.t3d_prop = PointerProperty(type=T3DProperties)
    init_object_props()

    # keymap
    wm = bpy.context.window_manager
    if wm.keyconfigs.addon is None: return
    km = wm.keyconfigs.addon.keymaps.new(name='Object Mode', space_type='EMPTY')
    km.keymap_items.new(SetActiveTile3D.bl_idname, 'S', 'PRESS')
    # you could do this for all controls, then they'd be configurable
    # but then you'd have to create thousands of operators?
    # (there is a 'modal keymap'?. can't find documentation)
    # https://docs.blender.org/api/blender_python_api_2_70_5/bpy.types.KeyMapItem.html#bpy.types.KeyMapItem
    addon_keymaps.append(km)

def unregister():
    bpy.utils.unregister_module(__name__)
    bpy.types.Scene.t3d_prop = None

    # keymap
    wm = bpy.context.window_manager
    if wm.keyconfigs.addon is None: return
    for km in addon_keymaps:
        wm.keyconfigs.addon.keymaps.remove(km)
    addon_keymaps.clear()

if __name__ == "__main__":
    register()
