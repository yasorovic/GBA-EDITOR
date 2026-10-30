"""Contrat du cycle de vie des contacts émis dans le C de scène."""


def test_exit_avertit_seulement_le_partenaire_actif_et_vivant():
    from codegen.runtime_codegen.physics.contacts import box_contact_lines

    code = "\n".join(box_contact_lines(
        "&a", "&b", "a.active&&b.active", "previous",
        [("on_collision_exit", "a_exit")], [("on_collision_exit", "b_exit")], ""))

    assert "if(!_c&&_p){" in code
    assert "if((&a)->active&&(&a)->alive&&(&b)->alive){ a_exit(&a,&b,_ta,_tb); }" in code
    assert "if((&b)->active&&(&b)->alive&&(&a)->alive){ b_exit(&b,&a,_tb,_ta); }" in code
