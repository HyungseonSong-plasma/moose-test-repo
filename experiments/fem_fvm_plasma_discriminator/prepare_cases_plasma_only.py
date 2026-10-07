#!/usr/bin/env python3
from pathlib import Path
import prepare_cases as base


def plasma_only_mesh(mesh_text: str) -> str:
    closing = "\n[]\n"
    if not mesh_text.endswith(closing):
        raise RuntimeError("unexpected Mesh section terminator")
    body = mesh_text[: -len(closing)]
    return body + r'''
  [plasma_only]
    type = BlockDeletionGenerator
    input = plasma_focus_ring
    operation = keep
    block = plasma
  []
[]
'''


base.MESH = plasma_only_mesh(base.MESH)

if __name__ == '__main__':
    cases = {
        'fem': base.fem(),
        'fvm': base.fvm(),
    }
    for name, text in cases.items():
        path = base.HERE / f'{name}_plasma_discriminator.i'
        path.write_text(text, encoding='utf-8')
        print(f'wrote {path}')
    print('mesh=plasma block only after preserving plasma interface side sets')
    print(f'dt={base.DT} s; steps={base.NSTEPS}; end_time={base.END_TIME} s')
    print(f'initial ne=ni={base.NE0} 1/m3; initial mean electron energy={base.MEAN_E0} eV')
    print(f'fixed ion mu={base.ION_MU} m2/(V s); fixed ion D={base.ION_D} m2/s')
    print('chemistry=OFF; heavy flow=OFF; wall-layer Joule suppression=OFF')
