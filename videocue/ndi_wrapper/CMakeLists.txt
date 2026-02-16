cmake_minimum_required(VERSION 3.17)

project(NDIlib VERSION 6.0.0)

set(CMAKE_MODULE_PATH ${PROJECT_SOURCE_DIR}/cmake/Modules)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_OSX_DEPLOYMENT_TARGET "10.12")
set(CMAKE_OSX_ARCHITECTURES "x86_64;arm64")

# Find pybind11 (installed via pip)
find_package(pybind11 REQUIRED)

# Set up NDI paths
if(NOT DEFINED NDI_PATH)
    message(FATAL_ERROR "NDI_PATH must be defined")
endif()

set(NDI_DIR "${NDI_PATH}")
set(NDI_INCLUDE_DIR "${NDI_PATH}/Include")
set(NDI_LICENSE_DIR "${NDI_PATH}")

if(WIN32)
    if(CMAKE_SIZEOF_VOID_P EQUAL 8)
        set(NDI_ARCH "x64")
    else()
        set(NDI_ARCH "x86")
    endif()
    set(NDI_LIBRARY_DIR "${NDI_PATH}/Lib/${NDI_ARCH}")
    set(NDI_LIBS "${NDI_LIBRARY_DIR}/Processing.NDI.Lib.${NDI_ARCH}.lib")
elseif(APPLE)
    set(NDI_LIBRARY_DIR "${NDI_PATH}/lib/${NDI_ARCH}")
    set(NDI_LIBS "${NDI_LIBRARY_DIR}/libndi.dylib")
elseif(UNIX)
    set(NDI_LIBRARY_DIR "${NDI_PATH}/lib/${NDI_ARCH}")
    set(NDI_LIBS "${NDI_LIBRARY_DIR}/libndi.so")
endif()

# Verify NDI SDK paths
if(NOT EXISTS "${NDI_INCLUDE_DIR}")
    message(FATAL_ERROR "NDI Include directory not found: ${NDI_INCLUDE_DIR}")
endif()
if(NOT EXISTS "${NDI_LIBRARY_DIR}")
    message(FATAL_ERROR "NDI Library directory not found: ${NDI_LIBRARY_DIR}")
endif()

file(GLOB INCLUDES ${CMAKE_CURRENT_SOURCE_DIR}/src/*.hpp)
file(GLOB SOURCES ${CMAKE_CURRENT_SOURCE_DIR}/src/*.cpp)

source_group("" FILES ${SOURCES} ${INCLUDES})

pybind11_add_module(NDIlib SHARED ${INCLUDES} ${SOURCES})

target_include_directories(NDIlib PRIVATE ${NDI_INCLUDE_DIR})
target_link_directories(NDIlib PRIVATE ${NDI_LIBRARY_DIR})
target_link_libraries(NDIlib PRIVATE pybind11::module ${NDI_LIBS})

set_target_properties(NDIlib PROPERTIES SKIP_RPATH TRUE)
set_target_properties(NDIlib PROPERTIES BUILD_RPATH_USE_ORIGIN TRUE)
set_target_properties(NDIlib PROPERTIES SKIP_BUILD_RPATH FALSE)
set_target_properties(NDIlib PROPERTIES BUILD_WITH_INSTALL_RPATH TRUE)
set_target_properties(NDIlib PROPERTIES INSTALL_RPATH_USE_LINK_PATH FALSE)
if(APPLE)
  set_target_properties(NDIlib PROPERTIES INSTALL_RPATH "@loader_path")
elseif(UNIX)
  set_target_properties(NDIlib PROPERTIES INSTALL_RPATH "$ORIGIN")
endif()

# install
install(
  TARGETS NDIlib
  RUNTIME DESTINATION ${CMAKE_INSTALL_PREFIX}
  LIBRARY DESTINATION ${CMAKE_INSTALL_PREFIX}
)
if(WIN32)
  install(
    FILES
    "${NDI_DIR}/Bin/${NDI_ARCH}/Processing.NDI.Lib.${NDI_ARCH}.dll"
    "${NDI_LICENSE_DIR}/Processing.NDI.Lib.Licenses.txt"
    DESTINATION ${CMAKE_INSTALL_PREFIX}
  )
elseif(APPLE)
  install(
    FILES
    "${NDI_LIBRARY_DIR}/libndi.dylib"
    "${NDI_LICENSE_DIR}/libndi_licenses.txt"
    DESTINATION ${CMAKE_INSTALL_PREFIX}
  )
elseif(UNIX)
  file(GLOB DLL "${NDI_LIBRARY_DIR}/libndi.so*")
  install(
    FILES
    ${DLL}
    "${NDI_LICENSE_DIR}/libndi_licenses.txt"
    DESTINATION ${CMAKE_INSTALL_PREFIX}
  )
endif()
