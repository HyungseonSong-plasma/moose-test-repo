#pragma once

#include "MeshGenerator.h"

class PhysicsBoundaryLayerRefineGenerator : public MeshGenerator
{
public:
  static InputParameters validParams();

  PhysicsBoundaryLayerRefineGenerator(const InputParameters & parameters);

protected:
  std::unique_ptr<MeshBase> generate() override;

private:
  std::unique_ptr<MeshBase> & _input;
  const std::vector<BoundaryName> _boundaries;
  const unsigned int _layers;
  const bool _enable_neighbor_refinement;
};
