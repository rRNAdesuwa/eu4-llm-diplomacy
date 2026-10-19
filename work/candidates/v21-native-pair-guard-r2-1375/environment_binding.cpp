#include "environment_binding.h"
namespace v21guard {
bool CompiledEnvironmentBinding::initialize(const eu4_spy_host18::Bootstrap& bootstrap) {
    if(attempted_)return false;attempted_=true;
    if(!native_.initialize(bootstrap,environment_)||environment_.mock||!environment_.exact_disk_and_loaded_image_verified)return false;
    ready_=true;return true;
}
}
