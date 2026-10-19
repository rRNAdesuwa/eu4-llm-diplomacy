"""Add the independently owned add/remove-rival command route to isolated V31."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT/'bridge/native/tag_diplomacy_1375_v31/src/work/candidates'


def edit(name, old, new):
    p = SRC/name; text = p.read_text()
    assert text.count(old) == 1, (name, old[:80], text.count(old))
    p.write_text(text.replace(old,new),newline='\n')


def main():
    names=('select_rival','remove_rival')
    h='v21-core-pair-nosend-r2-1375/pair_component.h'
    edit(h,'N_trade_favors_for_heir, N_warn\n};','N_trade_favors_for_heir, N_warn, N_select_rival, N_remove_rival\n};')
    edit(h,'ActionCount=118;','ActionCount=120;\nbool independent(Action action) noexcept;')
    c='v24-pair-send-core-r2-1375/pair_send.cpp'
    edit(c,'std::array<std::string_view, 118> names','std::array<std::string_view, 120> names')
    edit(c,'"trade_favors_for_heir","warn"}};','"trade_favors_for_heir","warn","select_rival","remove_rival"}};')
    edit(c,'if (i>=ActionCount) throw','if (i>=118) throw')
    edit(c,'return i<ActionCount&&bindings[i].mode;','return i<ActionCount&&(i>=118||bindings[i].mode);')
    edit(c,'return i<ActionCount?bindings[i].script:"";','return i<118?bindings[i].script:"";')
    edit(c,'bool legacy_cancel(Action action) noexcept {','bool independent(Action action) noexcept {const auto i=static_cast<unsigned>(action);return i>=118&&i<ActionCount;}\nbool legacy_cancel(Action action) noexcept {')
    codec='v26-gap-curry-bootstrap-1375/codec.h'
    edit(codec,'std::array<const char*,118> Names','std::array<const char*,120> Names')
    edit(codec,'"trade_favors_for_heir","warn"}};','"trade_favors_for_heir","warn","select_rival","remove_rival"}};')
    p=ROOT/'bridge/tag_actions_1375_v31.json';cfg=json.loads(p.read_text())
    cfg['actions']+=list(names)
    cfg['bindings'] += [dict(action=name,category='relations',native_family='add_rival' if name=='select_rival' else 'remove_rival',mode=True,script_key='',route='independent_command') for name in names]
    cfg['excluded']=[x for x in cfg['excluded'] if x['action'] not in names]
    p.write_text(json.dumps(cfg,indent=2)+'\n')
    port='v24-pair-send-port-r2-1375/'
    edit(port+'native_pair_engine.h','std::uint32_t extra_count{};\n};','std::uint32_t extra_count{};std::uint8_t independent_kind{};\n};')
    edit(port+'submission_guard.cpp','    if(!valid(e.stamp) || e.command<0x10000',r'''    if(e.independent_kind) {
        if(e.independent_kind>2 || !valid(e.stamp) || e.clone || e.command<0x10000 || (e.command&7) || e.stamp.game!=prepared_.game)return false;
        Address a=0;std::uint32_t u=0;std::uint8_t b=0;std::uint16_t w=0;std::int32_t s=0;
        const auto vt=e.independent_kind==1?0x1c55138:0x1c54a68;
        return at(e.command,0,a)&&a==env_.base+vt&&at(e.command,8,u)&&u==0x165
          &&at(e.command,0x10,b)&&!b&&at(e.command,0x18,a)&&!a&&at(e.command,0x28,a)&&!a
          &&at(e.command,0x30,a)&&a==15&&at(e.command,0x38,s)&&s==-1&&at(e.command,0x3c,u)&&!u
          &&at(e.command,0x40,w)&&!w&&at(e.command,0x44,u)&&u==(e.independent_kind==1?0x2faeu:0x2fafu)
          &&at(e.command,0x48,a)&&a==0xffff&&at(e.command,0x50,a)&&a==e.stamp.actor.value
          &&at(e.command,0x58,a)&&a==e.stamp.target.value;
    }
    if(!valid(e.stamp) || e.command<0x10000''')
    host='v26-gap-curry-bootstrap-1375/'
    edit(host+'bootstrap.cpp','#include "installer.h"','#include "installer.h"\n#include "native_rival.h"')
    edit(host+'bootstrap.cpp',' const auto result=job->core.invoke(packet.request,job->guard,job->engine,*job,packet.expires,&job->guard,env.image_base);\n const auto d=job->engine.diagnostics();',
         ' v21pair::SendResult result{};v24port::Diagnostics d{};\n'
         ' if(v21pair::independent(packet.request.action)) {\n'
         '   const auto r=tagcommand31::rival(packet.request,job->guard,job->platform,packet.expires,record);result=r.result;d=r.diagnostics;\n'
         ' } else {result=job->core.invoke(packet.request,job->guard,job->engine,*job,packet.expires,&job->guard,env.image_base);d=job->engine.diagnostics();}')
    build=ROOT/'bridge/native/tag_diplomacy_1375_v31/build_test.cmd';s=build.read_text().replace('(bootstrap installer)','(bootstrap installer native_rival)').replace('"%tagcommand31_out%\\bootstrap.obj"','"%tagcommand31_out%\\bootstrap.obj" "%tagcommand31_out%\\native_rival.obj"')
    build.write_text(s,newline='\n')
    print('120 TAG actions: 118 pair bindings plus independent add/remove rival; game_access=0')


if __name__=='__main__':main()
