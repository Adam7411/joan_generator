function baselock(widget_id, url, skin, parameters) {
    self = this;
    self.widget_id = widget_id;
    self.parameters = parameters;

    self.OnLockClick = OnLockClick;

    var callbacks = [
        { "selector": '#' + widget_id, "action": "click", "callback": self.OnLockClick }
    ];

    self.OnStateAvailable = OnStateAvailable;
    self.OnStateUpdate = OnStateUpdate;

    var monitored_entities = [
        { "entity": parameters.entity, "initial": self.OnStateAvailable, "update": self.OnStateUpdate }
    ];

    WidgetBase.call(self, widget_id, url, skin, parameters, monitored_entities, callbacks);

    function OnStateAvailable(self, state) {
        self.state = state.state;
        set_view(self, self.state);
    }

    function OnStateUpdate(self, state) {
        self.state = state.state;
        set_view(self, self.state);
    }

    function OnLockClick(self) {
        var args = {};
        if (self.state === "locked") {
            args = {
                "service": "lock/unlock",
                "entity_id": self.parameters.entity
            };
        } else {
            args = {
                "service": "lock/lock",
                "entity_id": self.parameters.entity
            };
        }
        self.call_service(self, args);
    }

    function set_view(self, state) {
        if (state === "locked") {
            self.set_icon(self, "icon", self.icons.icon_on); // Locked icon
            self.set_field(self, "icon_style", self.css.icon_style_active);
        } else {
            self.set_icon(self, "icon", self.icons.icon_off); // Unlocked icon
            self.set_field(self, "icon_style", self.css.icon_style_inactive);
        }
    }
}
