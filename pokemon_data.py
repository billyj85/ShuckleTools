import codecs
import sys
import os
from flask import json
import codecs



def pmdata():
    pokemon = os.path.dirname(os.path.abspath(os.path.realpath(__file__))) + "/docs/pokemon.min.json"
    with codecs.open(pokemon, "r", encoding="utf-8") as input_file:
        return json.load(input_file)

pokemons = pmdata()

candy12_evolvable = {10, 13, 16, 265}
candy12 = {10, 11, 12, 13, 14, 15, 16, 17, 18, 265, 266, 268, 267, 269}
candy25 = {19, 29, 32, 41, 43, 60, 63, 66, 69, 74, 92, 116, 133, 147, 152, 155, 158, 161, 165, 183, 187, 273, 363}
candy50 =    {21, 161, 163, 167, 170, 177, 194, 220, 261, 263, 300, 316, 339, 353, 361}

def pokemon_name(pid):
    return pokemons[str(pid)].get("name", str(pid))


