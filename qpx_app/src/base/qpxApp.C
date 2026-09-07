#include "qpxApp.h"
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
qpxApp::validParams()
{
  InputParameters params = MooseApp::validParams();
  params.set<bool>("use_legacy_material_output") = false;
  params.set<bool>("use_legacy_initial_residual_evaluation_behavior") = false;
  return params;
}

registerKnownLabel("qpxApp");

qpxApp::qpxApp(const InputParameters & parameters) : MooseApp(parameters)
{
  qpxApp::registerAll(_factory, _action_factory, _syntax);
  StochasticToolsApp::registerApps();
  NavierStokesApp::registerApps();
}

qpxApp::~qpxApp() {}

void
qpxApp::registerAll(Factory & f, ActionFactory & af, Syntax & syntax)
{
  ModulesApp::registerAllObjects<qpxApp>(f, af, syntax);
  Registry::registerObjectsTo(f, {"qpxApp"});
  Registry::registerActionsTo(af, {"qpxApp"});

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
qpxApp::registerApps()
{
  registerApp(qpxApp);
  ModulesApp::registerApps();
}

/***************************************************************************************************
 *********************** Dynamic Library Entry Points - DO NOT MODIFY ******************************
 **************************************************************************************************/
extern "C" void
qpxApp__registerAll(Factory & f, ActionFactory & af, Syntax & s)
{
  qpxApp::registerAll(f, af, s);
}
extern "C" void
qpxApp__registerApps()
{
  qpxApp::registerApps();
}
