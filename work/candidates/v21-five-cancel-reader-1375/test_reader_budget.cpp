// Include the actual implementation only in this isolated internal budget test.
// The main graph test separately links cancel_reader.obj.
#include "cancel_reader.cpp"
#include <iostream>
#include <stdexcept>
struct Fake final:v21pair::SyntheticReadPort {
    std::size_t calls{};
    bool read(std::uint64_t,void* out,std::size_t size) override {
        ++calls;std::memset(out,0,size);return true;
    }
};
void check(bool p){if(!p)throw std::runtime_error("budget assertion");}
template<class F>void rejected(F f){bool caught=false;try{f();}catch(...){caught=true;}check(caught);}
int main(){try{
    using namespace cancel1375;
    Fake source;Budget budget;std::vector<Read> trace;Reader reader(source,trace,budget);std::uint8_t byte{};
    budget.calls=19999;reader.read(0x10000,&byte,1);check(source.calls==1&&budget.calls==20000);
    rejected([&]{reader.read(0x10000,&byte,1);});check(source.calls==1);
    budget={512*1024-1,0};reader.read(0x10000,&byte,1);check(source.calls==2&&budget.bytes==512*1024);
    rejected([&]{reader.read(0x10000,&byte,1);});check(source.calls==2);
    budget={};std::vector<std::uint8_t> block(32769);reader.read(0x10000,block.data(),32768);check(source.calls==3);
    rejected([&]{reader.read(0x10000,block.data(),32769);});check(source.calls==3);
    rejected([&]{reader.read(0x10000,&byte,0);});rejected([&]{reader.read(Limit-1,block.data(),2);});check(source.calls==3);
    reader.read(Limit-1,&byte,1);check(source.calls==4);
    rejected([&]{reader.at<std::uint64_t>(Limit-8,8);});check(source.calls==4);
    // All of a two-pass capture shares one Budget object. A second Reader
    // cannot reset it merely by using another transcript.
    budget.calls=20000;std::vector<Read> second;Reader other(source,second,budget);
    rejected([&]{other.read(0x10000,&byte,1);});check(second.empty()&&source.calls==4);
    std::cout<<"budget_groups=6 exact_limits=true rejected_before_source_read=true shared_budget=true native_calls=0\n";
    return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}catch(...){return 2;}}
