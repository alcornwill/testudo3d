
# simple event system

listeners = {}

def subscribe(event, func):
    if event not in listeners:
        listeners[event] = []
    listeners[event].append(func)

def unsubscribe(event, func):
    listeners[event].remove(func)
    if not listeners[event]:
        del listeners[event]

def send_event(event, *args, **kw):
    if event in listeners:
        for func in listeners[event]:
            func(*args, **kw)