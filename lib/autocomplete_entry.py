"""
Modified from source: https://gist.github.com/uroshekic/11078820
Inspired by http://code.activestate.com/recipes/578253-an-entry-with-autocompletion-for-the-tkinter-gui/
Changes:
    - Fixed AttributeError: 'AutocompleteEntry' object has no attribute 'listbox'
    - Fixed scrolling listbox
    - Case-insensitive search
    - Added focus to entry field
    - Custom listbox length, listbox width matches entry field width
    - Custom matches function
"""

from tkinter import Tk, Entry, StringVar, Listbox, Button, END, ACTIVE
import re

def matches(fieldValue, acListEntry):
    pattern = re.compile('.*' + re.escape(fieldValue) + '.*', re.IGNORECASE)
    return re.match(pattern, acListEntry)

class AutocompleteEntry(Entry):
    def __init__(self, autocompleteList, *args, **kwargs):

        # Listbox length
        if 'listboxLength' in kwargs:
            self.listboxLength = kwargs['listboxLength']
            del kwargs['listboxLength']
        else:
            self.listboxLength = 8

        # Custom matches function
        if 'matchesFunction' in kwargs:
            self.matchesFunction = kwargs['matchesFunction']
            del kwargs['matchesFunction']
        else:                
            self.matchesFunction = matches

        # Custom set function
        if 'setFunction' in kwargs:
            self.setFunction = kwargs['setFunction']
            del kwargs['setFunction']
        else:
            def setvar(current_value, new_value):
                return new_value
            
            self.setFunction = setvar

        Entry.__init__(self, *args, **kwargs)
        self.focus()

        self.autocompleteList = autocompleteList
        
        if "textvariable" in kwargs:
            self.var = kwargs["textvariable"]
        else:
            self.var = self["textvariable"] = StringVar()

        self.var.trace_add('write', self.changed)
        self.bind("<Right>", self.selection)
        self.bind("<Up>", self.moveUp)
        self.bind("<Down>", self.moveDown)
        self.bind("<Escape>", self.closeListbox)
        
        self.listboxUp = False

    def changed(self, name, index, mode):
        if self.var.get() == '':
            if self.listboxUp:
                self.listbox.destroy()
                self.listboxUp = False
        else:
            words = self.comparison()
            if words:
                if not self.listboxUp:
                    self.listbox = Listbox(width=self["width"], height=self.listboxLength)
                    self.listbox.bind("<Button-1>", self.selection)
                    self.listbox.bind("<Right>", self.selection)
                    self.listbox.place(x=self.winfo_x(), y=self.winfo_y() + self.winfo_height())
                    self.listboxUp = True
                
                self.listbox.delete(0, END)
                for w in words:
                    self.listbox.insert(END,w)
            else:
                if self.listboxUp:
                    self.listbox.destroy()
                    self.listboxUp = False
        
    def selection(self, event):
        if self.listboxUp:
            self.var.set(self.setFunction(self.var.get(), self.listbox.get(ACTIVE)))
            self.listbox.destroy()
            self.listboxUp = False
            self.icursor(END)

    def moveUp(self, event):
        if self.listboxUp:
            if self.listbox.curselection() == ():
                index = '0'
            else:
                index = self.listbox.curselection()[0]
                
            if index != '0':                
                self.listbox.selection_clear(first=index)
                index = str(int(index) - 1)
                
                self.listbox.see(index) # Scroll!
                self.listbox.selection_set(first=index)
                self.listbox.activate(index)

    def moveDown(self, event):
        if self.listboxUp:
            if self.listbox.curselection() == ():
                index = '0'
            else:
                index = self.listbox.curselection()[0]
                
            if index != END:                        
                self.listbox.selection_clear(first=index)
                index = str(int(index) + 1)
                
                self.listbox.see(index) # Scroll!
                self.listbox.selection_set(first=index)
                self.listbox.activate(index)

    def comparison(self):
        return [ w for w in self.autocompleteList if self.matchesFunction(self.var.get(), w) ]

    def closeListbox(self, event=None):
        if hasattr(self, 'listbox'):
            self.listbox.destroy()
            self.listboxUp = False

if __name__ == '__main__':
    autocompleteList = [ 'Dora Lyons (7714)', 'Hannah Golden (6010)', 'Walker Burns (9390)' ]
    def matches(fieldValue, acListEntry):
        pattern = re.compile(re.escape(fieldValue) + '.*', re.IGNORECASE)
        return re.match(pattern, acListEntry)
    
    root = Tk()
    entry = AutocompleteEntry(autocompleteList, root, listboxLength=6, width=32, matchesFunction=matches)
    entry.grid(row=0, column=0)    
    Button(text='Python').grid(column=0)
    Button(text='Tkinter').grid(column=0)
    Button(text='Regular Expressions').grid(column=0)
    Button(text='Fixed bugs').grid(column=0)
    Button(text='New features').grid(column=0)
    Button(text='Check code comments').grid(column=0)
    root.mainloop()
