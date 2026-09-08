###############################################################################
# Physics dependency primer
#
# Builds the exact MOOSE/module + Squirrel/Crane/Zapdos dependency surface used
# by Physics, but deliberately does not compile Physics itself. The resulting
# image is the reusable compiler/build base for later Physics-only builds.
###############################################################################

MOOSE_DIR ?= /opt/physics_vendor/moose
FRAMEWORK_DIR := $(MOOSE_DIR)/framework

include $(FRAMEWORK_DIR)/build.mk
include $(FRAMEWORK_DIR)/moose.mk

ALL_MODULES                 := no
CHEMICAL_REACTIONS          := no
CONTACT                     := no
ELECTROMAGNETICS            := yes
EXTERNAL_PETSC_SOLVER       := no
FLUID_PROPERTIES            := yes
FSI                         := no
FUNCTIONAL_EXPANSION_TOOLS  := no
GEOCHEMISTRY                := no
HEAT_TRANSFER               := no
LEVEL_SET                   := no
MISC                        := no
NAVIER_STOKES               := yes
OPTIMIZATION                := no
PERIDYNAMICS                := no
PHASE_FIELD                 := no
POROUS_FLOW                 := no
RAY_TRACING                 := no
REACTOR                     := no
RDG                         := no
SOLID_MECHANICS             := no
STOCHASTIC_TOOLS            := yes
THERMAL_HYDRAULICS          := no
XFEM                        := no

include $(MOOSE_DIR)/modules/modules.mk

SQUIRREL_DIR ?= /opt/physics_vendor/squirrel
APPLICATION_DIR := $(SQUIRREL_DIR)
APPLICATION_NAME := squirrel
BUILD_EXEC := no
GEN_REVISION := no
include $(FRAMEWORK_DIR)/app.mk

CRANE_DIR ?= /opt/physics_vendor/crane
APPLICATION_DIR := $(CRANE_DIR)
APPLICATION_NAME := crane
BUILD_EXEC := no
GEN_REVISION := no
include $(FRAMEWORK_DIR)/app.mk

ZAPDOS_DIR ?= /opt/physics_vendor/zapdos
APPLICATION_DIR := $(ZAPDOS_DIR)
APPLICATION_NAME := zapdos
BUILD_EXEC := no
GEN_REVISION := no
include $(FRAMEWORK_DIR)/app.mk
