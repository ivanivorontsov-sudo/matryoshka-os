panels().forEach(function(p){p.remove()});
var t = new Panel;
t.location = "top"; t.height = 26;
t.addWidget("org.kde.plasma.digitalclock");
t.addWidget("org.kde.plasma.panelspacer");
t.addWidget("org.kde.plasma.systemtray");
var d = new Panel;
d.location = "bottom"; d.height = 52; d.floating = true; d.lengthMode = "fit"; d.alignment = "center";
d.addWidget("org.kde.plasma.icontasks");
