#include "PhysicsApp.h"
#include "Moose.h"
#include "AppFactory.h"
#include "ModulesApp.h"
#include "MooseSyntax.h"
#include "SquirrelApp.h"
#include "CraneApp.h"
#include "ZapdosApp.h"
#include "StochasticToolsApp.h"
#include "NavierStokesApp.h"

InputParameters
PhysicsApp::validParams()
{
  InputParameters params = MooseApp::validParams();
  params.set<bool>("use_legacy_material_output") = false;
  params.set<bool>("use_legacy_initial_residual_evaluation_behavior") = false;
  return params;
}

registerKnownLabel("PhysicsApp");

PhysicsApp::PhysicsApp(const InputParameters & parameters) : MooseApp(parameters)
{
  PhysicsApp::registerAll(_factory, _action_factory, _syntax);
  StochasticToolsApp::registerApps();
  NavierStokesApp::registerApps();
}

PhysicsApp::~PhysicsApp() {}

void
PhysicsApp::registerAll(Factory & f, ActionFactory & af, Syntax & syntax)
{
  ModulesApp::registerAllObjects<PhysicsApp>(f, af, syntax);
  Registry::registerObjectsTo(f, {"PhysicsApp"});
  Registry::registerActionsTo(af, {"PhysicsApp"});

  /* register custom execute flags, action syntax, etc. here */
  SquirrelApp::registerAll(f, af, syntax);
  CraneApp::registerAll(f, af, syntax);
  ZapdosApp::registerAll(f, af, syntax);
  NavierStokesApp::registerAll(f, af, syntax);

  /* register custom execute flags, action syntax, etc. here */
  syntax.registerActionSyntax("AddPeriodicControllers", "PeriodicControllers/*");
  syntax.registerActionSyntax("AddDriftDiffusionAction", "DriftDiffusionAction/*");
  syntax.registerActionSyntax("AddPeriodicRelativeNodalDifference", "PeriodicRelativeNodalDifference/*");
}

void
PhysicsApp::registerApps()
{
  registerApp(PhysicsApp);
  ModulesApp::registerApps();
}

/***************************************************************************************************
 *********************** Dynamic Library Entry Points - DO NOT MODIFY ******************************
 **************************************************************************************************/
extern "C" void
PhysicsApp__registerAll(Factory & f, ActionFactory & af, Syntax & s)
{
  PhysicsApp::registerAll(f, af, s);
}
extern "C" void
PhysicsApp__registerApps()
{
  PhysicsApp::registerApps();
}
