function on_start()
    for i = 1, actor:count() do
        local a = actor:get(i)
        if a and a.name == "Piege" then
            a:hide()
        end
    end
end
