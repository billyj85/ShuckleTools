import codecs
import os

from flask import json


def pmdata():
    pokemon = os.path.dirname(os.path.abspath(os.path.realpath(__file__))) + "/docs/pokemon.min.json"
    with codecs.open(pokemon, "r", encoding="utf-8") as input_file:
        return json.load(input_file)

pokemons = pmdata()

candy12_evolvable = {10, 13, 16, 265, 293}
candy12_high_candy = {11, 12, 14, 15, 17, 18, 266, 268, 267, 269, 294, 295}
candy12 = candy12_evolvable.union(candy12_high_candy)
candy25_evolvable = {19, 29, 32, 41, 43, 60, 63, 66, 69, 74, 92, 116, 133, 147, 152, 155, 158, 161, 165, 183, 187, 246,
                     252, 255, 258, 270, 273,
                     280, 287, 304, 355, 363}
candy25_high_candy = {20, 30, 31, 33, 34, 42, 44, 45, 61, 62, 64, 65, 67, 68, 70, 71, 75, 76, 93, 94, 117, 134, 135,
                      136, 148, 149, 153, 154, 156, 157, 159, 160, 162, 166, 169, 184, 188, 189, 247, 248, 253, 254,
                      256, 257, 259, 260, 271, 272, 274, 275, 281, 282, 288, 289, 298, 305, 306, 356, 364, 365, 477}
candy25 = candy25_evolvable.union(candy25_high_candy)
candy50 = {21, 72, 96, 118, 120, 138, 140, 161, 163, 167, 170, 177, 191, 194, 209, 216, 218, 220, 231, 261, 263, 285,
           296, 300, 307, 316, 318, 309, 325, 339, 341, 353, 361}


def pokemon_name(pid):
    return pokemons[str(pid)].get("name", str(pid))


