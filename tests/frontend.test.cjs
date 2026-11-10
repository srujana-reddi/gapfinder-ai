const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const app=fs.readFileSync(path.join(__dirname,'../public/static/app.js'),'utf8');
function context(state){
  const scope=vm.createContext({});
  vm.runInContext(app.slice(0,app.indexOf("$('#close-source').onclick")),scope);
  scope.fixture=state;
  vm.runInContext('data=fixture;ai=true;',scope);
  return scope;
}
function setup(state){return vm.runInContext('quizSetup()',context(state));}
test('empty account has actionable setup instead of a dead Generate button',()=>{
  const html=setup({topics:[],documents:[],pending:[]});
  assert.match(html,/Upload my syllabus & notes/);
  assert.doesNotMatch(html,/Try sample biology material/);
  assert.doesNotMatch(html,/id="quiz-form"/);
});
test('syllabus without matching notes shows the missing step',()=>{
  const state={topics:[{id:'t',name:'Photosynthesis',sources:[]}],documents:[],pending:[]};
  assert.match(setup(state),/Add notes for your syllabus topics/);
  state.documents=[{kind:'notes'}];
  assert.match(setup(state),/Your notes do not match/);
});
test('only sourced topics are offered and Generate is enabled',()=>{
  const html=setup({topics:[{id:'ready',name:'Ready topic',sources:[{}]},{id:'missing',name:'Missing topic',sources:[]}],documents:[{kind:'notes'}],pending:[]});
  assert.match(html,/<button type="submit">Generate my diagnostic/);
  assert.match(html,/<option value="ready">/);
  assert.doesNotMatch(html,/<option value="missing">/);
  assert.match(html,/1 of 2 topics/);
});
test('source citations cannot accidentally submit quiz forms',()=>{
  const scope=context({});
  const html=vm.runInContext("source({name:'<script>test</script>',page:1,section:'Intro',text:'Evidence'})",scope);
  assert.match(html,/<button type="button"/);
  assert.doesNotMatch(html,/<script>/);
});
