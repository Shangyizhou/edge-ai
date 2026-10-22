#pragma once

// 固定 fc-first 语法在首个 token 前生效，空 fc 后不存在合法追加工具分支。
inline constexpr const char *OUTPUT_GRAMMAR = R"GBNF(
root ::= ws "{" ws "\"fc\"" ws ":" ws calls ws "," ws "\"res\"" ws ":" ws string ws "}" ws
calls ::= "[" ws (string (ws "," ws string)*)? ws "]"
string ::= "\"" character* "\""
character ::= [^"\\\x00-\x1F] | "\\" (["\\/bfnrt] | "u" [0-9a-fA-F]{4})
ws ::= [ \t\n\r]*
)GBNF";
