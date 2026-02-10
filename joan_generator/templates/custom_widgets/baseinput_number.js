function baseinput_number(widget_id, url, skin, parameters) {
    self = this;
    self.widget_id = widget_id;
    self.parameters = parameters;

    self.OnPlusClick = OnPlusClick;
    self.OnMinusClick = OnMinusClick;

    var callbacks = [
        { "selector": '#' + widget_id + ' #plus', "action": "click", "callback": self.OnPlusClick },
        { "selector": '#' + widget_id + ' #minus', "action": "click", "callback": self.OnMinusClick }
    ];

    self.OnStateAvailable = OnStateAvailable;
    self.OnStateUpdate = OnStateUpdate;

    var monitored_entities = [
        { "entity": parameters.entity, "initial": self.OnStateAvailable, "update": self.OnStateUpdate }
    ];

    WidgetBase.call(self, widget_id, url, skin, parameters, monitored_entities, callbacks);

    function OnStateAvailable(self, state) {
        self.state = state.state;
        self.attributes = state.attributes;
        set_view(self, self.state);
    }

    function OnStateUpdate(self, state) {
        self.state = state.state;
        self.attributes = state.attributes;
        set_view(self, self.state);
    }

    function OnPlusClick(self) {
        var step = self.attributes.step || 1;
        var max = self.attributes.max || 100;
        var current = parseFloat(self.state);
        var next_val = current + step;
        if (next_val <= max) {
            var args = {
                "service": "input_number/set_value",
                "entity_id": self.parameters.entity,
                "value": next_val
            };
            self.call_service(self, args);
        }
    }

    function OnMinusClick(self) {
        var step = self.attributes.step || 1;
        var min = self.attributes.min || 0;
        var current = parseFloat(self.state);
        var next_val = current - step;
        if (next_val >= min) {
            var args = {
                "service": "input_number/set_value",
                "entity_id": self.parameters.entity,
                "value": next_val
            };
            self.call_service(self, args);
        }
    }

    function set_view(self, state) {
        self.set_field(self, "value", state);
    }
}
