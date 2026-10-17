#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>

#include "alliance-pending-membership.h"

using bridge::alliance_pending_membership::Result;
using bridge::alliance_pending_membership::inspect;

namespace {

struct Node {
    std::uintptr_t clone=0;
    std::uintptr_t previous=0;
    std::uintptr_t next=0;
};

struct Reader {
    const std::array<Node,3>* nodes=nullptr;
    bool fail=false;
    std::uintptr_t fail_address=0;

    bool operator()(std::uintptr_t address,std::uintptr_t& value) const noexcept {
        if (fail && address==fail_address) return false;
        for (const Node& node:*nodes) {
            const auto base=reinterpret_cast<std::uintptr_t>(&node);
            if (address==base) {
                value=node.clone; return true;
            }
            if (address==base+0x08) {
                value=node.previous; return true;
            }
            if (address==base+0x10) {
                value=node.next; return true;
            }
        }
        return false;
    }
};

static unsigned g_checks=0;
static unsigned g_failures=0;

static void check(bool condition,const char* name) {
    ++g_checks;
    if (!condition) {
        ++g_failures;
        std::printf("fixture_check_failed:%s\n",name);
    }
}

static std::uintptr_t address(const Node& node) noexcept {
    return reinterpret_cast<std::uintptr_t>(&node);
}

static void make_chain(std::array<Node,3>& nodes) noexcept {
    for (std::size_t index=0;index<nodes.size();++index) {
        nodes[index].clone=0x7000u+static_cast<std::uintptr_t>(index)*0x100u;
        nodes[index].previous=index==0?0:address(nodes[index-1]);
        nodes[index].next=index+1<nodes.size()?address(nodes[index+1]):0;
    }
}

static void test_empty_queue() {
    std::array<Node,3> nodes{};
    Reader reader{&nodes};
    check(inspect(0,0,0,0x1000,0x7000,64,reader)==Result::absent,
        "empty_queue_absent");
}

static void test_complete_absent() {
    std::array<Node,3> nodes{};
    make_chain(nodes);
    Reader reader{&nodes};
    check(inspect(address(nodes[0]),address(nodes[2]),3,0x1000,0x6000,64,reader)
        ==Result::absent,"complete_list_absent");
}

static void test_node_present() {
    std::array<Node,3> nodes{};
    make_chain(nodes);
    Reader reader{&nodes};
    check(inspect(address(nodes[0]),address(nodes[2]),3,address(nodes[1]),0x6000,64,reader)
        ==Result::present,"original_node_present");
}

static void test_clone_present() {
    std::array<Node,3> nodes{};
    make_chain(nodes);
    Reader reader{&nodes};
    check(inspect(address(nodes[0]),address(nodes[2]),3,0x1000,nodes[2].clone,64,reader)
        ==Result::present,"clone_present");
}

static void test_reader_failure() {
    std::array<Node,3> nodes{};
    make_chain(nodes);
    Reader reader{&nodes,true,address(nodes[1])+0x10};
    check(inspect(address(nodes[0]),address(nodes[2]),3,0x1000,0x6000,64,reader)
        ==Result::unknown,"reader_failure_unknown");
}

static void test_broken_chain_and_bound() {
    std::array<Node,3> nodes{};
    make_chain(nodes);
    nodes[1].previous=0xdead;
    Reader reader{&nodes};
    check(inspect(address(nodes[0]),address(nodes[2]),3,0x1000,0x6000,64,reader)
        ==Result::unknown,"broken_previous_unknown");

    make_chain(nodes);
    check(inspect(address(nodes[0]),address(nodes[2]),3,0x1000,0x6000,2,reader)
        ==Result::unknown,"count_over_bound_unknown");
}

} // namespace

int main() {
    test_empty_queue();
    test_complete_absent();
    test_node_present();
    test_clone_present();
    test_reader_failure();
    test_broken_chain_and_bound();
    std::printf("fixture=alliance_pending_membership checks=%u failures=%u\n",
        g_checks,g_failures);
    return g_failures==0?0:1;
}
