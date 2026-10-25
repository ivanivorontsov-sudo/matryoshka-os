panels().forEach(function(p){p.remove()});
var t = new Panel;
t.location = "top"; t.height = 32;
t.addWidget("org.kde.plasma.kickerdash");
t.addWidget("org.kde.plasma.panelspacer");
t.addWidget("org.kde.plasma.digitalclock");
t.addWidget("org.kde.plasma.panelspacer");
t.addWidget("org.kde.plasma.systemtray");
