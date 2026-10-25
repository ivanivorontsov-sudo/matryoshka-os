panels().forEach(function(p){p.remove()});
var p = new Panel;
p.location = "bottom"; p.height = 48; p.floating = false;
p.addWidget("org.kde.plasma.kickoff");
p.addWidget("org.kde.plasma.icontasks");
p.addWidget("org.kde.plasma.marginsseparator");
p.addWidget("org.kde.plasma.systemtray");
p.addWidget("org.kde.plasma.digitalclock");
p.addWidget("org.kde.plasma.showdesktop");
