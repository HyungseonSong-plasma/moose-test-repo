//* This file is part of the MOOSE framework
//* https://mooseframework.inl.gov
//*
//* All rights reserved, see COPYRIGHT for full restrictions
//* https://github.com/idaholab/moose/blob/master/COPYRIGHT
//*
//* Licensed under LGPL 2.1, please see LICENSE for details
//* https://www.gnu.org/licenses/lgpl-2.1.html
#include "PhysicsTestApp.h"
#include "PhysicsApp.h"
#include "Moose.h"
#include "AppFactory.h"
#include "MooseSyntax.h"

InputParameters
PhysicsTestApp::validParams()
{
  InputParameters params = PhysicsApp::validParams();
  params.set<bool>("use_legacy_material_output") = false;
  params.set<bool>("use_legacy_initial_residual_evaluation_behavior") = false;
  return params;
}

PhysicsTestApp::PhysicsTestApp(const InputParameters & parameters) : MooseApp(parameters)
{
  PhysicsTestApp::registerAll(
      _factory, _action_factory, _syntax, getParam<bool>("allow_test_objects"));
}

PhysicsTestApp::~PhysicsTestApp() {}

void
PhysicsTestApp::registerAll(Factory & f, ActionFactory & af, Syntax & s, bool use_test_objs)
{
  PhysicsApp::registerAll(f, af, s);
  if (use_test_objs)
  {
    Registry::registerObjectsTo(f, {"PhysicsTestApp"});
    Registry::registerActionsTo(af, {"PhysicsTestApp"});
  }
}

void
PhysicsTestApp::registerApps()
{
  registerApp(PhysicsApp);
  registerApp(PhysicsTestApp);
}

/***************************************************************************************************
 *********************** Dynamic Library Entry Points - DO NOT MODIFY ******************************
 **************************************************************************************************/
// External entry point for dynamic application loading
extern "C" void
PhysicsTestApp__registerAll(Factory & f, ActionFactory & af, Syntax & s)
{
  PhysicsTestApp::registerAll(f, af, s);
}
extern "C" void
PhysicsTestApp__registerApps()
{
  PhysicsTestApp::registerApps();
}
