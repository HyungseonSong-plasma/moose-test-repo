// Issue #652 G6: external, no-Physics-rebuild MOOSE FEProblem registration observer.
// Build only in pinned Physics OCI; preload for --check-input and bounded P3.
// Records names + factory types, not values or private rate-table contents.
#include <string>
#include <cstdio>
#include <cstdlib>
#include <dlfcn.h>
#include <fcntl.h>
#include <unistd.h>

class InputParameters;
class FEProblemBase
{
public:
  void addVariable(const std::string &, const std::string &, InputParameters &);
  void addKernel(const std::string &, const std::string &, InputParameters &);
  void addMaterial(const std::string &, const std::string &, InputParameters &);
  void addFunctorMaterial(const std::string &, const std::string &, InputParameters &);
  void addBoundaryCondition(const std::string &, const std::string &, InputParameters &);
  void addInitialCondition(const std::string &, const std::string &, InputParameters &);
};

using Original = void (*)(FEProblemBase *, const std::string &, const std::string &,
                          InputParameters &);

static Original original(const char *symbol)
{
  void *resolved = dlsym(RTLD_NEXT, symbol);
  if (!resolved)
  {
    std::fprintf(stderr, "G6_INTERPOSER_UNRESOLVED: %s\n", symbol);
    std::_Exit(83);
  }
  return reinterpret_cast<Original>(resolved);
}

static void append(const char *kind, const std::string &name, const std::string &type)
{
  const char *destination = std::getenv("G6_OWNER_TRACE");
  if (!destination || !*destination)
    std::_Exit(84);
  if (name.find('\n') != std::string::npos || name.find('\t') != std::string::npos ||
      type.find('\n') != std::string::npos || type.find('\t') != std::string::npos)
    std::_Exit(85);
  const int fd = open(destination, O_WRONLY | O_CREAT | O_APPEND | O_CLOEXEC | O_NOFOLLOW,
                      0600);
  if (fd < 0)
    std::_Exit(86);
  const std::string row = std::string("G6_OWNER\t") + kind + '\t' + name + '\t' + type + '\n';
  if (write(fd, row.data(), row.size()) != static_cast<ssize_t>(row.size()))
    std::_Exit(87);
  close(fd);
}

#define G6_WRAP(method, category, symbol)                                   \
  void FEProblemBase::method(const std::string &type, const std::string &name, \
                             InputParameters &params)                         \
  {                                                                          \
    static Original fn = original(symbol);                                   \
    fn(this, type, name, params);                                             \
    append(category, name, type);                                             \
  }

G6_WRAP(addVariable, "Variable",
        "_ZN13FEProblemBase11addVariableERKNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEES7_R15InputParameters")
G6_WRAP(addKernel, "Kernel",
        "_ZN13FEProblemBase9addKernelERKNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEES7_R15InputParameters")
G6_WRAP(addMaterial, "Material",
        "_ZN13FEProblemBase11addMaterialERKNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEES7_R15InputParameters")
G6_WRAP(addFunctorMaterial, "FunctorMaterial",
        "_ZN13FEProblemBase18addFunctorMaterialERKNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEES7_R15InputParameters")
G6_WRAP(addBoundaryCondition, "BC",
        "_ZN13FEProblemBase20addBoundaryConditionERKNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEES7_R15InputParameters")
G6_WRAP(addInitialCondition, "IC",
        "_ZN13FEProblemBase19addInitialConditionERKNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEES7_R15InputParameters")

__attribute__((constructor)) static void ready()
{
  const char *path = std::getenv("G6_OWNER_TRACE");
  if (!path || !*path)
    return;
  const int fd = open(path, O_WRONLY | O_CREAT | O_APPEND | O_CLOEXEC | O_NOFOLLOW, 0600);
  if (fd < 0)
    std::_Exit(88);
  constexpr char marker[] = "G6_PRELOAD_READY\n";
  if (write(fd, marker, sizeof(marker) - 1) != static_cast<ssize_t>(sizeof(marker) - 1))
    std::_Exit(89);
  close(fd);
}
