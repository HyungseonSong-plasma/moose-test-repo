// G7 independent fixed-state PETSc residual directional probe.
// Diagnostic-only LD_PRELOAD in the immutable build OCI. No PhysicsApp rebuild.
// No raw vector/matrix/field values emitted. Serial assembled NEWTON only.
#include <petscsnes.h>
#include <dlfcn.h>
#include <cstdint>
#include <cstdlib>
#include <cstdio>
#include <cstring>
#include <cmath>
#include <algorithm>

namespace {
constexpr double h = 1e-4;
constexpr double tol = 1e-8;
constexpr int directions = 3;

PetscErrorCode probe(SNES snes, Vec x, PetscInt n)
{
  PetscFunctionBeginUser;
  PetscMPIInt size;
  PetscCallMPI(MPI_Comm_size(PetscObjectComm((PetscObject)snes), &size));
  PetscCheck(size == 1, PETSC_COMM_SELF, PETSC_ERR_SUP, "G7_SERIAL_REQUIRED");
  Mat a = nullptr, p = nullptr;
  PetscCall(SNESGetJacobian(snes, &a, &p, nullptr, nullptr));
  PetscCheck(a && p, PETSC_COMM_SELF, PETSC_ERR_ARG_WRONGSTATE, "G7_NO_MATRIX");
  MatType type;
  PetscCall(MatGetType(a, &type));
  PetscCheck(type && (std::strcmp(type, MATSEQAIJ)==0 || std::strcmp(type, MATMPIAIJ)==0),
             PETSC_COMM_SELF, PETSC_ERR_SUP, "G7_EXPLICIT_AIJ_REQUIRED");
  PetscInt rows, cols;
  PetscCall(MatGetSize(a,&rows,&cols));
  PetscCheck(rows == n && cols == n, PETSC_COMM_SELF, PETSC_ERR_ARG_SIZ, "G7_MATRIX_SIZE");
  Vec base, direction, xp, xm, fp, fm, jv, fd0, fd1, fd2, r0, r1, restore, original;
  Vec *all[] = {&base,&direction,&xp,&xm,&fp,&fm,&jv,&fd0,&fd1,&fd2,&r0,&r1,&restore,&original};
  for (auto out : all) PetscCall(VecDuplicate(x,out));
  PetscCall(VecCopy(x,original));
  PetscCall(SNESComputeFunction(snes,x,base));
  PetscCall(SNESComputeJacobian(snes,x,a,p));
  PetscBool assembled;
  PetscCall(MatAssembled(a,&assembled));
  PetscCheck(assembled,PETSC_COMM_SELF,PETSC_ERR_ARG_WRONGSTATE,"G7_MATRIX_NOT_ASSEMBLED");
  PetscReal base_norm;
  PetscCall(VecNorm(base,NORM_2,&base_norm));
  for (int k=0;k<directions;++k)
  {
    const PetscScalar *xx;
    PetscScalar *vv;
    PetscCall(VecGetArrayRead(x,&xx));
    PetscCall(VecGetArray(direction,&vv));
    for (PetscInt i=0;i<n;++i)
    {
      std::uint64_t z = static_cast<std::uint64_t>(i)+0x9e3779b97f4a7c15ULL*(k+1);
      z = (z^(z>>30))*0xbf58476d1ce4e5b9ULL;
      z = (z^(z>>27))*0x94d049bb133111ebULL;
      z ^= z>>31;
      // Relative component perturbation with a nonzero absolute floor.
      vv[i] = ((z&1)?1.0:-1.0)*std::max(double(PetscAbsScalar(xx[i])),1e-6);
    }
    PetscCall(VecRestoreArray(direction,&vv));
    PetscCall(VecRestoreArrayRead(x,&xx));
    PetscCall(MatMult(a,direction,jv));
    Vec fds[] = {fd0,fd1,fd2};
    for (int level=0;level<3;++level)
    {
      const double step=h/std::pow(2.,level);
      PetscCall(VecWAXPY(xp,step,direction,x));
      PetscCall(VecWAXPY(xm,-step,direction,x));
      PetscCall(SNESComputeFunction(snes,xp,fp));
      PetscCall(SNESComputeFunction(snes,xm,fm));
      PetscCall(VecWAXPY(fds[level],-1.,fm,fp));
      PetscCall(VecScale(fds[level],1./(2.*step)));
    }
    // Two independent fourth-order Richardson estimates from central FD.
    PetscCall(VecCopy(fd1,r0));
    PetscCall(VecScale(r0,4./3.));
    PetscCall(VecAXPY(r0,-1./3.,fd0));
    PetscCall(VecCopy(fd2,r1));
    PetscCall(VecScale(r1,4./3.));
    PetscCall(VecAXPY(r1,-1./3.,fd1));
    PetscReal jnorm, fnorm, vnorm, err, conv, err_coarse;
    PetscCall(VecNorm(jv,NORM_2,&jnorm));
    PetscCall(VecNorm(r1,NORM_2,&fnorm));
    PetscCall(VecNorm(direction,NORM_2,&vnorm));
    const double scale=std::max(double(jnorm),double(fnorm));
    PetscCheck(std::isfinite(scale) && scale>0 && vnorm>0,PETSC_COMM_SELF,PETSC_ERR_FP,"G7_ZERO_OR_NONFINITE_DIRECTION");
    PetscCall(VecAXPY(r0,-1.,r1));
    PetscCall(VecNorm(r0,NORM_2,&conv));
    PetscCall(VecAXPY(r1,-1.,jv));
    PetscCall(VecNorm(r1,NORM_2,&err));
    PetscCall(VecAXPY(r0,1.,r1)); // R_coarse - Jv
    PetscCall(VecNorm(r0,NORM_2,&err_coarse));
    std::printf("G7_JVP %lld %d %.17g %.17g %.17g\n",
                (long long)n,k,double(err)/scale,double(conv)/scale,double(err_coarse)/scale);
    std::fflush(stdout);
  }
  PetscCall(SNESComputeFunction(snes,x,restore));
  PetscCall(VecAXPY(restore,-1.,base));
  PetscReal restoration;
  PetscCall(VecNorm(restore,NORM_2,&restoration));
  PetscBool same;
  PetscCall(VecEqual(x,original,&same));
  std::printf("G7_RESTORE %lld %d %.17g\n",(long long)n,int(same),
              double(restoration)/std::max(1.,double(base_norm)));
  std::fflush(stdout);
  for (auto out : all) PetscCall(VecDestroy(out));
  PetscFunctionReturn(PETSC_SUCCESS);
}
}

extern "C" PetscErrorCode SNESSolve(SNES snes,Vec b,Vec x)
{
  using Fn=PetscErrorCode (*)(SNES,Vec,Vec);
  static Fn real=reinterpret_cast<Fn>(dlsym(RTLD_NEXT,"SNESSolve"));
  if (!real) std::_Exit(89);
  const auto rc=real(snes,b,x);
  if (rc || !std::getenv("G7_JVP_MIN_DOF")) return rc;
  static bool seen=false;
  if (seen) return rc;
  SNESConvergedReason reason;
  PetscCall(SNESGetConvergedReason(snes,&reason));
  if (reason<=0) return rc;
  Vec solution=nullptr;
  PetscCall(SNESGetSolution(snes,&solution));
  if (!solution) return rc;
  PetscInt n=0, its=0;
  PetscCall(VecGetSize(solution,&n));
  PetscCall(SNESGetIterationNumber(snes,&its));
  const long minimum=std::strtol(std::getenv("G7_JVP_MIN_DOF"),nullptr,10);
  if (n<minimum || its<1) return rc;
  seen=true;
  std::printf("G7_FIXED_STATE %lld %lld\n",(long long)n,(long long)its);
  std::fflush(stdout);
  return probe(snes,solution,n);
}
