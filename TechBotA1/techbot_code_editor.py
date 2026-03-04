"""
TechBot Code Editor - Optimized VS Code-like Editor
Lightweight, fast, and feature-rich code editor
Memory optimized for better performance
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, font as tkfont
import os
import re
import threading
from pathlib import Path
import json
import subprocess
import queue
import sys

# ============== THEME ==============
BG_DARK = "#1e1e1e"
BG_SIDEBAR = "#252526"
BG_TABS = "#2d2d2d"
BG_STATUS = "#007acc"
BG_SEARCH = "#3c3c3c"
FG_TEXT = "#d4d4d4"
FG_DIM = "#858585"
FG_ACCENT = "#4ec9b0"
FG_KEYWORD = "#569cd6"
FG_STRING = "#ce9178"
FG_COMMENT = "#6a9955"
FG_NUMBER = "#b5cea8"
FG_FUNCTION = "#dcdcaa"
BORDER = "#3e3e42"
SELECTION_BG = "#264f78"
LINE_HIGHLIGHT = "#2a2a2a"

# ============== LANGUAGE PATTERNS ==============
# Optimized regex patterns for syntax highlighting
SYNTAX_PATTERNS = {
    ".py": [
        ("keyword", r'\b(False|None|True|and|as|assert|async|await|break|class|continue|def|del|elif|else|except|finally|for|from|global|if|import|in|is|lambda|nonlocal|not|or|pass|raise|return|try|while|with|yield)\b'),
        ("builtin", r'\b(print|input|len|range|str|int|float|list|dict|set|tuple|open|enumerate|zip|type|isinstance|super|property|staticmethod|classmethod)\b'),
        ("function", r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*(?=\()'),
        ("string", r'(["\'])(?:(?=(\\?))\2.)*?\1'),
        ("comment", r'#.*?$'),
        ("number", r'\b\d+\.?\d*\b'),
    ],
    ".js": [
        ("keyword", r'\b(async|await|break|case|catch|class|const|continue|debugger|default|delete|do|else|export|extends|finally|for|function|if|import|in|instanceof|let|new|return|static|super|switch|this|throw|try|typeof|var|void|while|with|yield)\b'),
        ("builtin", r'\b(console|window|document|Math|JSON|Array|Object|String|Number|Boolean|Promise|Set|Map)\b'),
        ("function", r'\b([a-zA-Z_$][a-zA-Z0-9_$]*)\s*(?=\()'),
        ("string", r'(["\'])(?:(?=(\\?))\2.)*?\1|`(?:[^`\\]|\\.)*`'),
        ("comment", r'//.*?$|/\*.*?\*/'),
        ("number", r'\b\d+\.?\d*\b'),
    ],
    ".html": [
        ("keyword", r'</?[a-zA-Z][a-zA-Z0-9]*'),
        ("builtin", r'\b(class|id|style|href|src|type|name|value|onclick)\b'),
        ("string", r'(["\'])(?:(?=(\\?))\2.)*?\1'),
        ("comment", r'<!--.*?-->'),
    ],
    ".css": [
        ("keyword", r'\b(body|div|span|p|a|ul|li|section|article|nav|header|footer|main|input|button|table|@media|@import)\b'),
        ("builtin", r'\b(color|background|margin|padding|font|width|height|border|display|position|flex|grid)\b'),
        ("string", r'(["\'])(?:(?=(\\?))\2.)*?\1'),
        ("comment", r'/\*.*?\*/'),
        ("number", r'\b\d+\.?\d*(px|em|rem|%|vh|vw)?\b'),
    ],
    ".json": [
        ("keyword", r'\b(true|false|null)\b'),
        ("string", r'"(?:[^"\\]|\\.)*"'),
        ("number", r'\b-?\d+\.?\d*([eE][+-]?\d+)?\b'),
    ]
}

# Tag colors mapping
TAG_COLORS = {
    "keyword": FG_KEYWORD,
    "builtin": FG_ACCENT,
    "function": FG_FUNCTION,
    "string": FG_STRING,
    "comment": FG_COMMENT,
    "number": FG_NUMBER,
}


class FileTreeNode:
    """Memory-efficient file tree node"""
    __slots__ = ['name', 'path', 'is_dir', 'children', 'loaded']
    
    def __init__(self, name, path, is_dir=False):
        self.name = name
        self.path = path
        self.is_dir = is_dir
        self.children = [] if is_dir else None
        self.loaded = False


class EditorTab:
    """Lightweight editor tab - loads content on demand"""
    __slots__ = ['path', 'widget', 'modified', 'scroll_pos', 'content_cache']
    
    def __init__(self, path, widget):
        self.path = path
        self.widget = widget
        self.modified = False
        self.scroll_pos = 0
        self.content_cache = None
    
    def get_content(self):
        """Get content from widget"""
        return self.widget.get("1.0", "end-1c")
    
    def set_modified(self, value):
        self.modified = value


class CodeEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("TechBot Code Editor - Optimized")
        self.root.geometry("1400x900")
        self.root.configure(bg=BG_DARK)
        
        # State management (memory efficient)
        self.tabs = {}  # path -> EditorTab
        self.active_tab = None
        self.workspace = os.getcwd()
        self.search_history = []
        self.undo_stack = {}  # path -> undo history
        
        # UI Setup
        self._setup_ui()
        self._setup_keybindings()
        
        # Performance optimization - delayed highlighting
        self.highlight_queue = []
        self.highlight_timer = None
        
    def _setup_ui(self):
        """Setup the main UI components"""
        # Menu Bar
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # File Menu
        file_menu = tk.Menu(menubar, tearoff=0, bg=BG_SIDEBAR, fg=FG_TEXT)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New File (Ctrl+N)", command=self.new_file)
        file_menu.add_command(label="Open File (Ctrl+O)", command=self.open_file)
        file_menu.add_command(label="Open Folder", command=self.open_folder)
        file_menu.add_separator()
        file_menu.add_command(label="Save (Ctrl+S)", command=self.save_file)
        file_menu.add_command(label="Save As (Ctrl+Shift+S)", command=self.save_as)
        file_menu.add_separator()
        file_menu.add_command(label="Close Tab (Ctrl+W)", command=self.close_tab)
        file_menu.add_command(label="Exit", command=self.root.quit)
        
        # Edit Menu
        edit_menu = tk.Menu(menubar, tearoff=0, bg=BG_SIDEBAR, fg=FG_TEXT)
        menubar.add_cascade(label="Edit", menu=edit_menu)
        edit_menu.add_command(label="Undo (Ctrl+Z)", command=self.undo)
        edit_menu.add_command(label="Redo (Ctrl+Y)", command=self.redo)
        edit_menu.add_separator()
        edit_menu.add_command(label="Find (Ctrl+F)", command=self.show_find)
        edit_menu.add_command(label="Replace (Ctrl+H)", command=self.show_replace)
        edit_menu.add_separator()
        edit_menu.add_command(label="Comment Line (Ctrl+/)", command=self.toggle_comment)
        
        # View Menu
        view_menu = tk.Menu(menubar, tearoff=0, bg=BG_SIDEBAR, fg=FG_TEXT)
        menubar.add_cascade(label="View", menu=view_menu)
        view_menu.add_command(label="Toggle Explorer (Ctrl+B)", command=self.toggle_sidebar)
        view_menu.add_command(label="Zoom In (Ctrl++)", command=self.zoom_in)
        view_menu.add_command(label="Zoom Out (Ctrl+-)", command=self.zoom_out)
        
        # Main horizontal container
        self.main_h_paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, 
                                            bg=BORDER, sashwidth=2, bd=0)
        self.main_h_paned.pack(fill=tk.BOTH, expand=True)
        
        # Sidebar (File Explorer)
        self.sidebar = tk.Frame(self.main_h_paned, bg=BG_SIDEBAR, width=280)
        self.main_h_paned.add(self.sidebar)
        
        # Explorer header
        explorer_header = tk.Frame(self.sidebar, bg=BG_SIDEBAR, height=35)
        explorer_header.pack(fill=tk.X)
        explorer_header.pack_propagate(False)
        tk.Label(explorer_header, text="EXPLORER", bg=BG_SIDEBAR, fg=FG_DIM, 
                font=("Consolas", 9, "bold")).pack(side=tk.LEFT, padx=10, pady=8)
        
        # File tree
        tree_frame = tk.Frame(self.sidebar, bg=BG_SIDEBAR)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        self.file_tree = ttk.Treeview(tree_frame, show="tree", selectmode="browse")
        tree_scroll = ttk.Scrollbar(tree_frame, command=self.file_tree.yview)
        self.file_tree.configure(yscrollcommand=tree_scroll.set)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.file_tree.pack(fill=tk.BOTH, expand=True)
        
        # Style the treeview
        style = ttk.Style()
        style.theme_use('default')
        style.configure("Treeview", background=BG_SIDEBAR, foreground=FG_TEXT, 
                       fieldbackground=BG_SIDEBAR, borderwidth=0)
        style.map('Treeview', background=[('selected', SELECTION_BG)])
        
        self.file_tree.bind("<Double-1>", self.on_tree_double_click)
        self.file_tree.bind("<<TreeviewOpen>>", self.on_tree_expand)
        
        # Right side vertical container
        self.main_v_paned = tk.PanedWindow(self.main_h_paned, orient=tk.VERTICAL,
                                            bg=BORDER, sashwidth=2, bd=0)
        self.main_h_paned.add(self.main_v_paned)
        
        # Top right container (Tabs and Editor)
        right_top_container = tk.Frame(self.main_v_paned, bg=BG_DARK)
        self.main_v_paned.add(right_top_container, minsize=400)
        
        # Tab bar
        self.tab_bar = tk.Frame(right_top_container, bg=BG_TABS, height=35)
        self.tab_bar.pack(fill=tk.X)
        self.tab_bar.pack_propagate(False)
        
        self.tab_buttons = {}  # path -> button
        
        # Run Button in tab bar
        run_btn = tk.Button(self.tab_bar, text="▶ Run", font=("Consolas", 10, "bold"), 
                            bg=FG_COMMENT, fg="white", relief=tk.FLAT, 
                            command=self.run_current_file, padx=10)
        run_btn.pack(side=tk.RIGHT, padx=5, pady=2)
        
        # Editor area
        self.editor_container = tk.Frame(right_top_container, bg=BG_DARK)
        self.editor_container.pack(fill=tk.BOTH, expand=True)
        
        # Search panel (hidden by default)
        self.search_panel = tk.Frame(right_top_container, bg=BG_SEARCH, height=60)
        self.search_var = tk.StringVar()
        self.replace_var = tk.StringVar()
        
        search_label = tk.Label(self.search_panel, text="Find:", bg=BG_SEARCH, fg=FG_TEXT)
        search_label.grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.search_entry = tk.Entry(self.search_panel, textvariable=self.search_var, 
                                     bg=BG_DARK, fg=FG_TEXT, insertbackground=FG_TEXT)
        self.search_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        
        replace_label = tk.Label(self.search_panel, text="Replace:", bg=BG_SEARCH, fg=FG_TEXT)
        replace_label.grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.replace_entry = tk.Entry(self.search_panel, textvariable=self.replace_var,
                                      bg=BG_DARK, fg=FG_TEXT, insertbackground=FG_TEXT)
        self.replace_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        
        btn_frame = tk.Frame(self.search_panel, bg=BG_SEARCH)
        btn_frame.grid(row=0, column=2, rowspan=2, padx=5)
        tk.Button(btn_frame, text="Find Next", command=self.find_next, bg=BG_STATUS, 
                 fg="white", relief=tk.FLAT).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_frame, text="Replace", command=self.replace_current, bg=BG_STATUS,
                 fg="white", relief=tk.FLAT).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_frame, text="Replace All", command=self.replace_all, bg=BG_STATUS,
                 fg="white", relief=tk.FLAT).pack(side=tk.LEFT, padx=2)
        tk.Button(btn_frame, text="×", command=self.hide_search, bg=BG_SEARCH,
                 fg=FG_TEXT, relief=tk.FLAT, width=2).pack(side=tk.LEFT, padx=5)
        
        self.search_panel.columnconfigure(1, weight=1)
        
        # Status bar
        self.status_bar = tk.Frame(self.root, bg=BG_STATUS, height=25)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        self.status_bar.pack_propagate(False)
        
        self.status_label = tk.Label(self.status_bar, text="Ready", bg=BG_STATUS, 
                                     fg="white", font=("Consolas", 9))
        self.status_label.pack(side=tk.LEFT, padx=10)
        
        self.pos_label = tk.Label(self.status_bar, text="Ln 1, Col 1", bg=BG_STATUS,
                                 fg="white", font=("Consolas", 9))
        self.pos_label.pack(side=tk.RIGHT, padx=10)
        
        # Bottom right container (Terminal)
        self.terminal_container = tk.Frame(self.main_v_paned, bg=BG_DARK)
        self.main_v_paned.add(self.terminal_container, minsize=100)
        
        term_header = tk.Frame(self.terminal_container, bg=BG_SEARCH, height=25)
        term_header.pack(fill=tk.X)
        term_header.pack_propagate(False)
        tk.Label(term_header, text="TERMINAL OUTPUT", bg=BG_SEARCH, fg=FG_TEXT, 
                font=("Consolas", 9, "bold")).pack(side=tk.LEFT, padx=10)
        
        clear_term_btn = tk.Button(term_header, text="Clear", bg=BG_SIDEBAR, fg=FG_TEXT, 
                                  relief=tk.FLAT, bd=0, command=self.clear_terminal)
        clear_term_btn.pack(side=tk.RIGHT, padx=5, pady=2)
        
        self.terminal_output = tk.Text(self.terminal_container, bg="black", fg="#00ff00",
                                      font=("Consolas", 10), bd=0, highlightthickness=0,
                                      state=tk.DISABLED, padx=5, pady=5)
        term_scroll = tk.Scrollbar(self.terminal_container, command=self.terminal_output.yview)
        term_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.terminal_output.configure(yscrollcommand=term_scroll.set)
        self.terminal_output.pack(fill=tk.BOTH, expand=True)
        
        # Queue for thread-safe terminal updates
        self.term_queue = queue.Queue()
        self.root.after(100, self.process_term_queue)
        
        # Initialize workspace
        self.refresh_file_tree()
        
    def _setup_keybindings(self):
        """Setup keyboard shortcuts"""
        bindings = {
            '<Control-n>': lambda e: self.new_file(),
            '<Control-o>': lambda e: self.open_file(),
            '<Control-s>': lambda e: self.save_file(),
            '<Control-Shift-S>': lambda e: self.save_as(),
            '<Control-w>': lambda e: self.close_tab(),
            '<Control-f>': lambda e: self.show_find(),
            '<Control-h>': lambda e: self.show_replace(),
            '<Control-b>': lambda e: self.toggle_sidebar(),
            '<Control-slash>': lambda e: self.toggle_comment(),
            '<Control-plus>': lambda e: self.zoom_in(),
            '<Control-minus>': lambda e: self.zoom_out(),
            '<Escape>': lambda e: self.hide_search(),
        }
        
        for key, func in bindings.items():
            self.root.bind(key, func)
    
    def create_editor_widget(self, parent):
        """Create a text editor widget with line numbers"""
        container = tk.Frame(parent, bg=BG_DARK)
        
        # Line numbers canvas
        line_canvas = tk.Canvas(container, width=50, bg=BG_DARK, 
                               highlightthickness=0, bd=0)
        line_canvas.pack(side=tk.LEFT, fill=tk.Y)
        
        # Text widget
        text_widget = tk.Text(container, bg=BG_DARK, fg=FG_TEXT, 
                             insertbackground="white", font=("Consolas", 11),
                             undo=True, maxundo=-1, autoseparators=True,
                             bd=0, highlightthickness=0, padx=10, pady=10,
                             selectbackground=SELECTION_BG, selectforeground=FG_TEXT,
                             wrap=tk.NONE)
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Scrollbars
        y_scroll = tk.Scrollbar(container, command=text_widget.yview)
        y_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        text_widget.configure(yscrollcommand=y_scroll.set)
        
        x_scroll = tk.Scrollbar(parent, orient=tk.HORIZONTAL, command=text_widget.xview)
        text_widget.configure(xscrollcommand=x_scroll.set)
        
        # Configure syntax highlighting tags
        for tag, color in TAG_COLORS.items():
            text_widget.tag_configure(tag, foreground=color)
        
        text_widget.tag_configure("current_line", background=LINE_HIGHLIGHT)
        
        # Bind events
        text_widget.bind("<KeyRelease>", lambda e: self.on_text_change(text_widget))
        text_widget.bind("<Button-1>", lambda e: self.update_cursor_position(text_widget))
        text_widget.bind("<KeyPress>", lambda e: self.update_cursor_position(text_widget))
        
        # Auto-indent and bracket completion
        text_widget.bind("<Return>", self.handle_return)
        for char in ['(', '[', '{', '"', "'"]:
            text_widget.bind(char, lambda e, c=char: self.handle_brackets(e, c))
            
        # Context menu
        ctx_menu = tk.Menu(text_widget, tearoff=0, bg=BG_SIDEBAR, fg=FG_TEXT)
        ctx_menu.add_command(label="Cut", command=lambda: text_widget.event_generate("<<Cut>>"))
        ctx_menu.add_command(label="Copy", command=lambda: text_widget.event_generate("<<Copy>>"))
        ctx_menu.add_command(label="Paste", command=lambda: text_widget.event_generate("<<Paste>>"))
        ctx_menu.add_separator()
        ctx_menu.add_command(label="Select All", command=lambda: text_widget.tag_add("sel", "1.0", "end"))
        
        text_widget.bind("<Button-3>", lambda e: ctx_menu.post(e.x_root, e.y_root))
        
        # Line numbers update
        def update_line_nums(*args):
            self.draw_line_numbers(text_widget, line_canvas)
        
        text_widget.bind("<Configure>", update_line_nums)
        text_widget.bind("<KeyRelease>", update_line_nums, add="+")
        y_scroll.config(command=lambda *args: (text_widget.yview(*args), update_line_nums()))
        
        return container, text_widget, line_canvas
    
    def draw_line_numbers(self, text_widget, canvas):
        """Draw line numbers efficiently"""
        canvas.delete("all")
        
        # Get visible line range
        first_visible = text_widget.index("@0,0")
        last_visible = text_widget.index(f"@0,{text_widget.winfo_height()}")
        
        first_line = int(first_visible.split(".")[0])
        last_line = int(last_visible.split(".")[0])
        
        current_line = int(text_widget.index("insert").split(".")[0])
        
        for line_num in range(first_line, last_line + 1):
            dline = text_widget.dlineinfo(f"{line_num}.0")
            if dline:
                y = dline[1]
                color = FG_TEXT if line_num == current_line else FG_DIM
                canvas.create_text(45, y, anchor="ne", text=str(line_num),
                                 fill=color, font=("Consolas", 10))
    
    def on_text_change(self, text_widget):
        """Handle text changes - queue highlighting"""
        if self.active_tab:
            self.active_tab.set_modified(True)
            self.update_tab_title(self.active_tab.path)
            
            # Queue syntax highlighting (debounced)
            if self.highlight_timer:
                self.root.after_cancel(self.highlight_timer)
            
            self.highlight_timer = self.root.after(300, 
                lambda: self.highlight_syntax(text_widget, self.active_tab.path))
    
    def highlight_syntax(self, text_widget, path):
        """Apply syntax highlighting efficiently"""
        ext = os.path.splitext(path)[1].lower()
        patterns = SYNTAX_PATTERNS.get(ext, [])
        
        if not patterns:
            return
        
        # Clear existing tags
        for tag in TAG_COLORS.keys():
            text_widget.tag_remove(tag, "1.0", "end")
        
        # Get visible content only for performance
        content = text_widget.get("1.0", "end-1c")
        
        # Apply patterns
        for tag, pattern in patterns:
            for match in re.finditer(pattern, content, re.MULTILINE):
                start_idx = f"1.0+{match.start()}c"
                end_idx = f"1.0+{match.end()}c"
                text_widget.tag_add(tag, start_idx, end_idx)
    
    def update_cursor_position(self, text_widget):
        """Update cursor position in status bar"""
        self.root.after(10, lambda: self._update_pos(text_widget))
    
    def _update_pos(self, text_widget):
        cursor_pos = text_widget.index("insert")
        line, col = cursor_pos.split(".")
        self.pos_label.config(text=f"Ln {line}, Col {int(col)+1}")
        
        # Highlight current line
        text_widget.tag_remove("current_line", "1.0", "end")
        text_widget.tag_add("current_line", f"{line}.0", f"{line}.end+1c")
        
    def handle_return(self, event):
        """Auto-indentation on Enter key"""
        text_widget = event.widget
        current_line_idx = text_widget.index("insert linestart")
        current_line = text_widget.get(current_line_idx, "insert")
        
        # Calculate indentation (spaces/tabs at the start of the line)
        indent = len(current_line) - len(current_line.lstrip())
        indent_str = current_line[:indent]
        
        # If line ends with ':' add extra indent level
        if current_line.rstrip().endswith(":"):
            indent_str += "    "
            
        text_widget.insert("insert", "\n" + indent_str)
        text_widget.see("insert")
        return "break" # Prevent default return action
        
    def handle_brackets(self, event, char):
        """Auto-close brackets and quotes"""
        text_widget = event.widget
        matching = {'(': ')', '[': ']', '{': '}', '"': '"', "'": "'"}
        
        text_widget.insert("insert", char)
        text_widget.insert("insert", matching[char])
        text_widget.mark_set("insert", "insert-1c")
        return "break" # Prevent default insertion action
    
    def new_file(self):
        """Create a new file"""
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("All Files", "*.*"), ("Python", "*.py"), ("JavaScript", "*.js"),
                      ("HTML", "*.html"), ("CSS", "*.css"), ("JSON", "*.json")]
        )
        if path:
            with open(path, 'w') as f:
                f.write("")
            self.open_file_path(path)
            self.refresh_file_tree()
    
    def open_file(self):
        """Open a file dialog"""
        path = filedialog.askopenfilename(
            filetypes=[("All Files", "*.*"), ("Python", "*.py"), ("JavaScript", "*.js"),
                      ("HTML", "*.html"), ("CSS", "*.css"), ("JSON", "*.json")]
        )
        if path:
            self.open_file_path(path)
    
    def open_file_path(self, path):
        """Open a specific file path"""
        path = os.path.abspath(path)
        
        # If already open, just switch to it
        if path in self.tabs:
            self.switch_tab(path)
            return
        
        # Create editor
        container, text_widget, line_canvas = self.create_editor_widget(self.editor_container)
        
        # Load content
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            text_widget.insert("1.0", content)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open file: {e}")
            container.destroy()
            return
        
        # Create tab
        tab = EditorTab(path, text_widget)
        self.tabs[path] = tab
        
        # Create tab button
        tab_btn_frame = tk.Frame(self.tab_bar, bg=BG_TABS)
        tab_btn_frame.pack(side=tk.LEFT, padx=1)
        
        filename = os.path.basename(path)
        btn = tk.Button(tab_btn_frame, text=filename, bg=BG_SIDEBAR, fg=FG_TEXT,
                       relief=tk.FLAT, bd=0, padx=10, pady=5,
                       command=lambda p=path: self.switch_tab(p))
        btn.pack(side=tk.LEFT)
        
        close_btn = tk.Button(tab_btn_frame, text="×", bg=BG_SIDEBAR, fg=FG_TEXT,
                             relief=tk.FLAT, bd=0, width=2,
                             command=lambda p=path: self.close_tab_by_path(p))
        close_btn.pack(side=tk.LEFT)
        
        self.tab_buttons[path] = (tab_btn_frame, btn, close_btn, container)
        
        # Switch to new tab
        self.switch_tab(path)
        
        # Initial highlight
        self.highlight_syntax(text_widget, path)
        self.draw_line_numbers(text_widget, line_canvas)
        
        self.status_label.config(text=f"Opened: {filename}")
    
    def switch_tab(self, path):
        """Switch to a different tab"""
        if path not in self.tabs:
            return
        
        # Hide current tab
        if self.active_tab:
            old_container = self.tab_buttons[self.active_tab.path][3]
            old_container.pack_forget()
            self.tab_buttons[self.active_tab.path][1].config(bg=BG_TABS)
        
        # Show new tab
        self.active_tab = self.tabs[path]
        container = self.tab_buttons[path][3]
        container.pack(fill=tk.BOTH, expand=True)
        self.tab_buttons[path][1].config(bg=BG_SIDEBAR)
        
        # Focus
        self.active_tab.widget.focus_set()
        self.update_cursor_position(self.active_tab.widget)
        
        self.status_label.config(text=f"Active: {os.path.basename(path)}")
        self.root.title(f"TechBot Code Editor - {path}")
    
    def close_tab(self):
        """Close active tab"""
        if self.active_tab:
            self.close_tab_by_path(self.active_tab.path)
    
    def close_tab_by_path(self, path):
        """Close tab by path"""
        if path not in self.tabs:
            return
        
        tab = self.tabs[path]
        
        # Check if modified
        if tab.modified:
            result = messagebox.askyesnocancel("Save?", 
                f"Save changes to {os.path.basename(path)}?")
            if result is None:  # Cancel
                return
            elif result:  # Yes
                self.save_file_by_path(path)
        
        # Remove tab
        btn_frame, _, _, container = self.tab_buttons[path]
        btn_frame.destroy()
        container.destroy()
        
        del self.tabs[path]
        del self.tab_buttons[path]
        
        # Switch to another tab if available
        if path == self.active_tab.path:
            self.active_tab = None
            if self.tabs:
                self.switch_tab(list(self.tabs.keys())[0])
    
    def save_file(self):
        """Save active file"""
        if self.active_tab:
            self.save_file_by_path(self.active_tab.path)
    
    def save_file_by_path(self, path):
        """Save file by path"""
        if path not in self.tabs:
            return
        
        tab = self.tabs[path]
        content = tab.get_content()
        
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            tab.set_modified(False)
            self.update_tab_title(path)
            self.status_label.config(text=f"Saved: {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save: {e}")
    
    def save_as(self):
        """Save as new file"""
        if not self.active_tab:
            return
        
        new_path = filedialog.asksaveasfilename(
            defaultextension=os.path.splitext(self.active_tab.path)[1],
            filetypes=[("All Files", "*.*")]
        )
        
        if new_path:
            content = self.active_tab.get_content()
            try:
                with open(new_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                # Close old tab and open new
                old_path = self.active_tab.path
                self.close_tab_by_path(old_path)
                self.open_file_path(new_path)
                self.refresh_file_tree()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save: {e}")
    
    def update_tab_title(self, path):
        """Update tab title to show modified status"""
        if path in self.tab_buttons:
            btn = self.tab_buttons[path][1]
            filename = os.path.basename(path)
            if self.tabs[path].modified:
                btn.config(text=f"● {filename}")
            else:
                btn.config(text=filename)
    
    def open_folder(self):
        """Open a folder as workspace"""
        folder = filedialog.askdirectory()
        if folder:
            self.workspace = folder
            self.refresh_file_tree()
            self.status_label.config(text=f"Workspace: {os.path.basename(folder)}")
    
    def refresh_file_tree(self):
        """Refresh the file explorer tree"""
        self.file_tree.delete(*self.file_tree.get_children())
        
        if os.path.isdir(self.workspace):
            self.populate_tree(self.workspace, "")
    
    def populate_tree(self, path, parent):
        """Populate tree with files and folders"""
        try:
            items = sorted(os.listdir(path), 
                          key=lambda x: (not os.path.isdir(os.path.join(path, x)), x.lower()))
            
            for item in items:
                # Skip hidden and common ignore patterns
                if item.startswith('.') or item in ['__pycache__', 'node_modules', 'venv']:
                    continue
                
                full_path = os.path.join(path, item)
                is_dir = os.path.isdir(full_path)
                
                icon = "📁" if is_dir else "📄"
                node = self.file_tree.insert(parent, "end", text=f"{icon} {item}",
                                            values=[full_path], open=False)
                
                # Add placeholder for lazy loading
                if is_dir:
                    self.file_tree.insert(node, "end", text="...")
        except PermissionError:
            pass
    
    def on_tree_expand(self, event):
        """Handle tree expansion - lazy load children"""
        node = self.file_tree.focus()
        if not node:
            return
        
        # Check if placeholder exists
        children = self.file_tree.get_children(node)
        if children and self.file_tree.item(children[0])['text'] == "...":
            # Remove placeholder
            self.file_tree.delete(children[0])
            
            # Load actual children
            path = self.file_tree.item(node)['values'][0]
            self.populate_tree(path, node)
    
    def on_tree_double_click(self, event):
        """Handle double click on tree item"""
        selection = self.file_tree.selection()
        if not selection:
            return
        
        item = selection[0]
        path = self.file_tree.item(item)['values'][0]
        
        if os.path.isfile(path):
            self.open_file_path(path)
    
    def toggle_sidebar(self):
        """Toggle sidebar visibility"""
        if self.sidebar.winfo_ismapped():
            self.main_h_paned.forget(self.sidebar)
        else:
            self.main_h_paned.add(self.sidebar, before=self.main_h_paned.panes()[0])
    
    def show_find(self):
        """Show find panel"""
        self.search_panel.pack(side=tk.BOTTOM, fill=tk.X, before=self.editor_container)
        self.search_entry.focus_set()
    
    def show_replace(self):
        """Show replace panel"""
        self.show_find()
        self.replace_entry.focus_set()
    
    def hide_search(self):
        """Hide search panel"""
        self.search_panel.pack_forget()
    
    def find_next(self):
        """Find next occurrence"""
        if not self.active_tab:
            return
        
        search_text = self.search_var.get()
        if not search_text:
            return
        
        text_widget = self.active_tab.widget
        
        # Start from current cursor position
        start_pos = text_widget.index("insert")
        pos = text_widget.search(search_text, start_pos, stopindex="end")
        
        if pos:
            # Select found text
            end_pos = f"{pos}+{len(search_text)}c"
            text_widget.tag_remove("sel", "1.0", "end")
            text_widget.tag_add("sel", pos, end_pos)
            text_widget.mark_set("insert", end_pos)
            text_widget.see(pos)
        else:
            # Wrap around
            pos = text_widget.search(search_text, "1.0", stopindex=start_pos)
            if pos:
                end_pos = f"{pos}+{len(search_text)}c"
                text_widget.tag_remove("sel", "1.0", "end")
                text_widget.tag_add("sel", pos, end_pos)
                text_widget.mark_set("insert", end_pos)
                text_widget.see(pos)
            else:
                messagebox.showinfo("Find", "No matches found")
    
    def replace_current(self):
        """Replace current selection"""
        if not self.active_tab:
            return
        
        text_widget = self.active_tab.widget
        
        try:
            if text_widget.tag_ranges("sel"):
                text_widget.delete("sel.first", "sel.last")
                text_widget.insert("insert", self.replace_var.get())
                self.find_next()
        except tk.TclError:
            self.find_next()
    
    def replace_all(self):
        """Replace all occurrences"""
        if not self.active_tab:
            return
        
        search_text = self.search_var.get()
        replace_text = self.replace_var.get()
        
        if not search_text:
            return
        
        text_widget = self.active_tab.widget
        content = text_widget.get("1.0", "end-1c")
        new_content = content.replace(search_text, replace_text)
        count = content.count(search_text)
        
        if count > 0:
            text_widget.delete("1.0", "end")
            text_widget.insert("1.0", new_content)
            messagebox.showinfo("Replace All", f"Replaced {count} occurrence(s)")
        else:
            messagebox.showinfo("Replace All", "No matches found")
    
    def toggle_comment(self):
        """Toggle line comment"""
        if not self.active_tab:
            return
        
        text_widget = self.active_tab.widget
        ext = os.path.splitext(self.active_tab.path)[1].lower()
        
        # Determine comment syntax
        comment_chars = {
            '.py': '#',
            '.js': '//',
            '.css': '//',
            '.html': '<!--',
        }
        
        comment = comment_chars.get(ext, '#')
        
        try:
            # Get selected lines
            start_line = int(text_widget.index("sel.first").split(".")[0])
            end_line = int(text_widget.index("sel.last").split(".")[0])
        except tk.TclError:
            # No selection, use current line
            start_line = end_line = int(text_widget.index("insert").split(".")[0])
        
        for line_num in range(start_line, end_line + 1):
            line_start = f"{line_num}.0"
            line_content = text_widget.get(line_start, f"{line_num}.end")
            
            if line_content.strip().startswith(comment):
                # Uncomment
                idx = line_content.find(comment)
                text_widget.delete(f"{line_num}.{idx}", f"{line_num}.{idx+len(comment)}")
                if line_content[idx+len(comment):idx+len(comment)+1] == ' ':
                    text_widget.delete(f"{line_num}.{idx}", f"{line_num}.{idx+1}")
            else:
                # Comment
                text_widget.insert(line_start, f"{comment} ")
    
    def zoom_in(self):
        """Increase font size"""
        if self.active_tab:
            current_font = self.active_tab.widget.cget("font")
            if isinstance(current_font, tuple):
                family, size = current_font[0], current_font[1]
            else:
                family, size = "Consolas", 11
            
            self.active_tab.widget.config(font=(family, size + 1))
    
    def zoom_out(self):
        """Decrease font size"""
        if self.active_tab:
            current_font = self.active_tab.widget.cget("font")
            if isinstance(current_font, tuple):
                family, size = current_font[0], max(current_font[1] - 1, 6)
            else:
                family, size = "Consolas", 10
            
            self.active_tab.widget.config(font=(family, size))
    
    def undo(self):
        """Undo last change"""
        if self.active_tab:
            try:
                self.active_tab.widget.edit_undo()
            except tk.TclError:
                pass
    
    def redo(self):
        """Redo last undone change"""
        if self.active_tab:
            try:
                self.active_tab.widget.edit_redo()
            except tk.TclError:
                pass
                
    # --- Terminal Execution ---
    def write_to_terminal(self, text, color="#00ff00"):
        self.term_queue.put((text, color))
        
    def process_term_queue(self):
        while not self.term_queue.empty():
            text, color = self.term_queue.get()
            self.terminal_output.config(state=tk.NORMAL)
            
            # create tag if needed
            tag_name = f"color_{color.replace('#', '')}"
            self.terminal_output.tag_configure(tag_name, foreground=color)
            
            self.terminal_output.insert("end", text, tag_name)
            self.terminal_output.see("end")
            self.terminal_output.config(state=tk.DISABLED)
        
        self.root.after(100, self.process_term_queue)
        
    def clear_terminal(self):
        self.terminal_output.config(state=tk.NORMAL)
        self.terminal_output.delete("1.0", tk.END)
        self.terminal_output.config(state=tk.DISABLED)
        
    def run_current_file(self):
        """Execute the currently active file in the terminal pane"""
        if not self.active_tab:
            self.write_to_terminal("No active file to run.\n", "red")
            return
            
        path = self.active_tab.path
        
        # Save first if modified
        if self.active_tab.modified:
            self.save_file()
            
        ext = os.path.splitext(path)[1].lower()
        
        cmd = []
        if ext == ".py":
            cmd = [sys.executable, path]
        elif ext == ".js":
            cmd = ["node", path]
        else:
            self.write_to_terminal(f"Don't know how to run {ext} files.\n", "yellow")
            return
            
        self.write_to_terminal(f"\n> Running: {path}\n", "cyan")
        
        def _run_process():
            try:
                # Use subprocess to run
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                          text=True, bufsize=1, cwd=os.path.dirname(path))
                
                # Read stdout
                for line in process.stdout:
                    self.write_to_terminal(line)
                    
                # Read stderr
                err = process.stderr.read()
                if err:
                    self.write_to_terminal(err, "red")
                    
                process.wait()
                self.write_to_terminal(f"\n[Finished with Exit Code {process.returncode}]\n", 
                                      "#888888" if process.returncode == 0 else "red")
            except Exception as e:
                self.write_to_terminal(f"Error executing file: {e}\n", "red")
                
        threading.Thread(target=_run_process, daemon=True).start()


def main():
    root = tk.Tk()
    editor = CodeEditor(root)
    root.mainloop()


if __name__ == "__main__":
    main()
