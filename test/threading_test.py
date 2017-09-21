
# was testing threading, it doesn't work
# but maybe it will one day

import time
from threading import Thread
import bpy
t3d = bpy.context.scene.t3d

def replace(seq, replacementRules, n):
    for i in range(n):
        newseq = ""
        for element in seq:
            newseq = newseq + replacementRules.get(element,element)
        seq = newseq
    return seq

def draw(commands, rules):
    for b in commands:
        result = rules[b]
        if callable(result):
            result()
            time.sleep(0.3)
        else:
            draw(result, rules)
            
def snake_kolam():
    # Python36\Lib\turtledemo\lindenmayer.py
    t3d.cursor.tile3d = 'Suzanne'

    def r():
        t3d.right(45)

    def l():
        t3d.left(45)
        
    def f():
        t3d.forward(3)
        
    snake_rules = {"-":r, "+":l, "f":f, "b":"f+f+f--f--f+f+f"}
    snake_replacementRules = {"b": "b+f+b--f--b+f+b"}
    snake_start = "b--f--b--f"

    drawing = replace(snake_start, snake_replacementRules, 0)

    t3d.up()
    t3d.backward(25)
    t3d.down()
    draw(drawing, snake_rules)
            
thread = Thread(target=snake_kolam)
thread.start()
#thread.join()