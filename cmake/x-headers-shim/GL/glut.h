/* afni-win: the X11/OpenGL headers of AFNI_WIN_X_HEADERS describe a POSIX
 * system; with _WIN32 visible they would include windows.h and switch to the
 * Win32 calling convention (cmake/afni-nox.cmake). */
#pragma push_macro("_WIN32")
#undef _WIN32
#include_next <GL/glut.h>
#pragma pop_macro("_WIN32")
