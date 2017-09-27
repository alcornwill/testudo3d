# Intro
Testudo3D (T3D) is a 3D tilemap addon for blender  
Modular level design is a ubiquitous technique in the game industry  
3D tilemaps are a higher level of modularity, useful to artists who want to produce more content, faster.  
Most of all tilemapping is fun to use, and removes the tedium of placing modules by hand.  
But this tool could have some interesting uses beyond game development.  
  
T3D is easy to use, and requires a minimal amount of configuration.  
Setting up the rules is admittidly a bit intimidating, but once it's done you benefit from the power of auto-tiling.  
By only using features already within blender,
scenes created with T3D are always compatible with conventionally modelled scenes.   
T3D is designed to let you sketch out the structure of your scene before you add the details by hand

Using Blender as a level editor is a radical choice, but there are compelling reasons to try it:
* jump back and forth between modeling and level design
* use the program you are already comfortable with
* game engine independent (no platform lock-in!)
* blender is free and open source (all addons are open source too)
* blender is easy to script and extend with addons, you can tailor it to your needs

__Note__ you will have to figure out the __export__ part yourself.  
If you can't figure out how to import a scene made with blender into your game engine, 
this tool will not be much use to you as a level editor.

# Contact
If you find a bug or something to be improved, please contact __alcornwill@gmail.com__

# Turtle Graphics?
[wikipedia](https://en.wikipedia.org/wiki/Turtle_graphics)  
(This is where the name comes from, Testudo = Tortoise in latin)  
to see an example of turtle graphics, run the unit tests in 'test/run_tests.py'  
**NOTE** you must have **blender in your environment variables** to run the tests  
Python also has some turtle graphics samples you can run  **(Python36\Lib\turtledemo)**

# Install
* download .zip from github
* __unzip__
* find __testudo3d/testudo3d/__ folder (contains 4 .py files)
* __zip it__
* in Blender, install __testudo3d.zip__ (User Prefs > Addons > Install From File)

You will find all the tool's operators in the __T3D tab__ (3DView > T3D)

# Workflow
setup
* Create a set of tiles (just objects)
* use **Setup 3D Tiles** to automatically create groups for every object in the scene and arrange them nicely
* Create the rules .txt file

Then you can start painting in Auto Mode.  
Use multiple tilesets, multiple roots, and multiple layers to add lots of detail.  
from there you can render, or export to your game engine.  
The __testudo3d/samples/__ folder contains lots of blends with tiles and rules already setup,
if you just want to get started.  
 
Manual Mode basically __requires no setup__, if you don't care about auto-tiling (see below)

# Tiles
a **Tile** is just a group, T3D uses [dupligroups](https://docs.blender.org/manual/en/dev/editors/3dview/object/properties/duplication/dupligroup.html)  
i.e. to create a **tile**, create any object and add it to a group  
There is no restriction on the type of object (you can use lamps etc.)  
You can even use multiple objects (just add multiple objects to the group)  
Objects can be any size, though you probably want them to be 1x1x1  

a tile 'instance' is a [group instance](http://blender-manual-i18n.readthedocs.io/ja/latest/modeling/groups.html) (3DView > Add > Group Instance)  
Since they're just objects, you can add, delete, move them around and rotate them by hand if you want  
__Tip__: use __Align Tiles__ to align objects to grid (3DView > T3D > Utils > Align Tiles)

# Roots
Notice that when you run Manual/Auto Mode, an empty called 'Root' will pop up in your scene  
The root can have any transformation, it does not have to stay at 0,0,0  
This helps you create levels that feel more organic, as you can break right-angles by rotating the root  

__Tip__ if you have multiple roots in a 'chain', you can use constraints to connect them  
This is what the __Connect Roots__ utility does (3DView > T3D > Utils > Connect Roots)  
First select the 'child' root, __then__ select the 'parent' root.  
  
**NOTE** when you enter manual/auto mode, the currently selected object will be used as the root  
__Strange things may happen__ if you select a tile and then enter manual/auto mode, be careful to always select the root    
In fact the root object can be anything. It doesn't have to be an Empty.  
If no object is selected, a new 'Root' will be created  

# Layers
Notice the __Layer__ number in the T3D Tools panel  
Tiles will be created/deleted in the active layer  
Since a cell can only be occupied by one tile at a time, layers are needed to build up complex scenes  
__e.g.__ create a road on layer 0, houses on layer 1, street lamps on layer 2, ...
   
__NOTE__ you may have noticed the junk that Auto Mode creates in the layer 'below' the active layer  
This is important junk that Auto Mode needs to work properly  
They are actually just empties, and they signify whether a cell is 'occupied' or not  
You can delete them, it just means Auto Mode will 'forget' which cells are occupied   
They also store the tileset (hence if you __rename a tileset__ this will break, for this use __Rename Tileset__)  

# Manual VS Auto Mode
In **Manual Mode** you can choose specific tiles and paint with them  
In **Auto Mode** the tiles are chosen using **rules** (aka **auto-tiling**)

# Rules
Auto-tiling rules are contained in a rules file (.txt)  
Writing a rules file by hand is tedious and error prone  
Sometimes a rules file can be auto-generated (see RoomGen operator)  
There are plenty of examples of rules files in the **testudo3d/samples/** folder  
The template rules file __testudo3d/samples/rules.txt__
contains all possible bitmask permutations (64) should you ever want to define them all

Format:  
```
[bitmask] [tile]  
```
e.g.  
```
001001 TileA  
001010 TileB  
110001 TileC
```  
each bit of the bitmask corresponds to a direction:  
```
DUWSEN
Down Up West South East North
```  
```
0 = unoccipied  
1 = occupied  
```
e.g. in the bitmask '000001' only North is occupied  
__NOTE__:  tiles will be rotated in Z if applicable

**Limitations**: note that the bitmask doesn't contain information for **diagonals** or **terrain**  
The 6-bit design was chosen in favor of simplicity, but it could be extended  

# Manual Mode
_(3DView > T3D > Tools > Manual Mode)_  
__Manual Mode__ has a very simple setup, it only requires that your blend contains some groups  
Since T3D has no GUI for browsing tiles however, setting the __active tile__ can be awkward  
The easiest way is to __duplicate the window__ (Window > Duplicate Window)  
Then open the scene with your tiles in one window, and your working scene in another   
(requires __User Prefs > Interface > Global Scene__ be disabled)  
When in Manual Mode, select a tile and press __S__ to set it as the active tile

# Auto Mode
_(3DView > T3D > Tools > Auto Mode)_  
To use __Auto Mode__, you first have to tell T3D where to find your __rules__  
Use the '__+__' button under Auto Mode and navigate to the rules __.txt__ file  
The __name__ of the rules file determines the name of the tileset  
Note that you can add multiple tilesets  
Auto Mode will be __greyed out__ until you __select__ the tileset 

# Link
_(3DView > T3D > Utils > Link)_  
Blender's linking system is very useful for keeping your work organized  
You may want to save each tileset in separate .blend files and link them into another .blend where you create your scene  
the __Link__ utility will help you do this by quickly linking just the groups and scenes from any .blend file  

# Room Gen 
_(3DView > T3D > Utils > Room Gen)_  
If you want to create a building with **Walls**, **Floors** and **Ceilings**,
you may be able to use **RoomGen** to generate your **tiles** and **rules**  
* create 3 groups __Wall__, __Floor__ and __Ceiling__
* choose the name
* press **Room Gen** 
* press **Setup 3D Tiles**

this should generate your tiles and a rules .txt file in your .blend directory   
(for an example see __testudo3d/samples/house.blend__)
# Make Tiles Real
(3DView > T3D > Utils > Make Tiles Real)  
Since tiles are just groups, it is easy to change the tile by hand __(Properties > Object > Duplication > Group)__  
If your tile is itself composed of objects or groups,
you may want to change it without changing all the other tiles of the same type  
Blender does have the __Make Duplicates Real__  operator, but unfortunately it only works recursively  
__Make Tiles Real__ will only make the first level of group instances real

# Controls
Key | Action
----|----
__TAB__ | toggle mouse paint
__CURSOR KEYS__ | move
__CTRL UP/DOWN__ | move up and down
__CTRL LEFT/RIGHT__ | strafe left/right
__SHIFT CURSOR KEYS__ | move faster
__ENTER__ | paint
__X__ | delete
__CTRL C/V__ | copy/paste
__G__ | grab
__B__ | select region
__S__ | sample
__[__ | increment brush size
__]__ | decrement brush size
__ESCAPE__ | escape/cancel

**NOTE:** controls are not configurable yet (sorry)