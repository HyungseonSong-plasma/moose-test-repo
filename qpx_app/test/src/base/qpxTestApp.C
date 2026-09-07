//* This file is part of the MOOSE framework
//* https://mooseframework.inl.gov
//*
//* All rights reserved, see COPYRIGHT for full restrictions
//* https://github.com/idaholab/moose/blob/master/COPYRIGHT
//*
//* Licensed under LGPL 2.1, please see LICENSE for details
//* https://www.gnu.org/licenses/lgpl-2.1.html
#include "qpxTestApp.h"
#include "qpxApp.h"
#include "Moose.h"
#include "AppFactory.h"
#include "MooseSyntax.h"

InputParameters
qpxTestApp::validParams()
{
  InputParameters params = qpxApp::validParams();
  params.set<bool>("use_legacy_material_output") = false;
  params.set<bool>("use_legacy_initial_residual_evaluation_behavior") = false;
  return params;
}

qpxTestApp::qpxTestApp(const InputParameters & parameters) : MooseApp(parameters)
{
  qpxTestApp::registerAll(
      _factory, _action_factory, _syntax, getParam<bool>("allow_test_objects"));
}

qpxTestApp::~qpxTestApp() {}

void
qpxTestApp::registerAll(Factory & f, ActionFactory & af, Syntax & s, bool use_test_objs)
{
  qpxApp::registerAll(f, af, s);
  if (use_test_objs)
  {
    Registry::registerObjectsTo(f, {"qpxTestApp"});
    Registry::registerActionsTo(af, {"qpxTestApp"});
  }
}

void
qpxTestApp::registerApps()
{
  registerApp(qpxApp);
  registerApp(qpxTestApp);
}

/***************************************************************************************************
 *********************** Dynamic Library Entry Points - DO NOT MODIFY ******************************
 **************************************************************************************************/
// External entry point for dynamic application loading
extern "C" void
qpxTestApp__registerAll(Factory & f, ActionFactory & af, Syntax & s)
{
  qpxTestApp::registerAll(f, af, s);
}
extern "C" void
qpxTestApp__registerApps()
{
  qpxTestApp::registerApps();
}
