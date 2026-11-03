"""Le nom de scène qui commence par un chiffre : la constante appelée par un script est celle que le header définit."""
from scripting.api import scene_constant
from codegen.c_names import sym as c_sym


def test_scene_constant_digit_prefix_matches_header():
    assert scene_constant("01_Kinematic") == f"SCENE_IDX_{c_sym('01_Kinematic').upper()}"
    assert scene_constant("Victory") == "SCENE_IDX_VICTORY"
