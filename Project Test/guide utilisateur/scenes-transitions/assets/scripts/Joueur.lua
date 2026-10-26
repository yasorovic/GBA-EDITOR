function on_update()
    self.position = self.position + input:get_axis("horizontal", "vertical") * 2
end
