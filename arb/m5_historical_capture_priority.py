"""Historical *priority hints*, never current signed-execution evidence.

One route fingerprint per distinct starting mint from successful signed atomic
and rollback verification in GitHub Actions run 43485684936, commit 797098bf.
The run independently verified 55 starts / 123 routes. These 55 hashes are
the first graph-order verified route for each of those 55 starts, recovered
from source-fixtures plus all ten per-shard verified-route metrics artifacts.

A hash only influences order. It neither bypasses current source account
authentication nor substitutes for fresh signed-and-rollback verification.
No live execution approval or profitability assertion.
"""
import hashlib
import json

ORIGIN_RUN=43485684936
ORIGIN_VERIFIED_STARTS=55
ORIGIN_VERIFIED_ROUTES=123
PRIORITY_ROUTE_HASHES=frozenset([

    "40456b919968a3412c50db923bc7381fee4b9ae7d24a04b6426f3ac42703a8ca",
    "2e6834ad24b12f17fe06ccec7efc264c626258218d23b24723e0450727dee2ec",
    "3c3fc5d3a12994c0ac600222392c8f89ce1b7c4341d9ae043538ce5fa88de979",
    "bc50bb2bcc930a9fedd273d997f6fca1873903f71e98dd062285114efc9a5475",
    "668a2b5cf37d4f9ccac04339cf1f12f5a44209ba4cc24256abcb93899dd66750",
    "17d1679a064257c1a212484554ccbae6bfb550cc214db1e7a4b548f8da2ab493",
    "ba0a440da80924e686a68eb1539643e1b0d6ffde81112a1cbb09169e1273cb34",
    "c4b46bc19251bbf57c956eaddd0a4cde16277b6d76d460c18a778ae764cf443d",
    "5df14d487fbaabd307a858094e19bc7cbc5f25eb3a136d246cbe5e151bfc99a6",
    "dcba891a4438dd4b859206571160d805e8e7ead91e334e9556183cbd371faaa8",
    "935961f5431d1d305d7367363ed1eca5b18152531eb11ad0dbf42b1db57fe33c",
    "f4a37eba285c18ae45851c2651a9f47c61d6845e0c6d8586022a2321e92fefe4",
    "7ceb8012793256d497c5ac1f195e96cb6114c97e5bd1e747c20c59331ae3c382",
    "e630e83201f916e93df0d3f57babf584b07be3626422243938f330f291468e9c",
    "8042d69edcecc658a7bfc35a37ea85a4f7cb065786864c10b4a3ffb0c5842819",
    "e429ff5711e10e72f58ea4032c191c069d70f0a4a70ae39311bdbbed083d51ed",
    "b8a913a8bc0c89047ee22532ff930ce9062996972f247cf32441234313f9d57d",
    "4de698ee9c6df1b3bf925d598f58e022aeb9d1c6b0c38825723d8c03b6a3b26c",
    "2b6ae7ae9f0aaed294c698dc8fe07ba12679ee1a2c30534997364f92c2544cae",
    "c63652a7145dccc062337023344171c7167cde953eb753a2497f87e27ffe4154",
    "2c42c11d26bc6a4a226a664eff787901461b1e454ff54facf7ac73bfa321c0f9",
    "b19239ada1e11ccf5093becfce722c4c5d3d93552f304d793cacacf61fd14b03",
    "034a4beb16a5714d5ed79c8ee31528db1ea57b3a8dfa4654bbf94b5ededcacd6",
    "395f927764efcdd459771c0a5945b0abb8d0ed47c33d0fc3499fffb2f1662966",
    "a23f2f056f7a7d8ef4874c3c9155a91669c76475eb2cf87930df85d8c95f5943",
    "c2a46d9c3339f7f7932d08c4ab4c85b4a56f4c5256a1ab039df41d9ef0668129",
    "c66c1491b386e8101645d11c73e5807f3e1c695410a93b06dcee174c0ab2c399",
    "8dbfa3fd956b27a4edcc6321ef8bb506282a7937749f7b5d04a8cd939cff00ad",
    "8e0ea4620a07964b428633e8421356c2ecd98f247ad8697b8bd87abc36077a22",
    "f8d1186b7daf3ab9469eb777a4646927efc40df8c6cb0e6a7f8e32795d465dd4",
    "3aa872940e3b26ededcfb8e65309fafaf6b03b4f0547cec7ea29bfb87cacff77",
    "73f5efab07dbe1ca6d97bcc549022058a068893efc52cbe700757ef51d8922e0",
    "308363a4c8c55501feddeaec07e417d44d25467c78b91d7f472b3e586f5c3d9f",
    "180e48d4df1f3aa9d80af7651981207721e4167030586ce503766d3e0c38d2d5",
    "afc475503f746d7ddc69d071d21188ab8812dd6a9429eebacd9debf313ae6fde",
    "0aa373a2563d055c351752b2147437c2f7c825fb3358898979686b2c69a08055",
    "eb16f2c589c017bd457344f3090c7b3456c1b8ff914dae844176af5fcf3058a3",
    "11dd599c2b36623a03f541ecf6c441cd9965c3af592a6d378158944caefd3528",
    "168069831293337fd86640fdd14489b918b4bcaa61585406fe60aac5c9b41098",
    "fb06236d38db5622e0a86d5f849afb9f1d39e5aaa677f344d75122aa78d57246",
    "7d194d536cbd15e8aedfd3f956dee30d6ea0c8f0bc7da627108b70b036bcfcb2",
    "fd3425e6077eb6e6cbf23e8cdf97573d00b0a6191f66715046ddf94b80a420bc",
    "0546f609df12da71f0df2bf0767a83079ea4cd6dce454a2ebd043eb61c9cf2f5",
    "ce88a860f142c95bc465ee90371172db0c71d8648b584fce6317985b466c0ccb",
    "3475a0d2a68df809496685f867b1e5e782173e20773cf07ff9b84a9a2d89d02c",
    "f34a9b226eb24c86ddaf6cbc0e0d0797944326055e531a1fb3aadce6cb507a6d",
    "de77a2a50e6ac8f66e521d951782db2443d0ccbf9cd43e1157e0bb29ec153c99",
    "71091f48a9eec95a38110402157f40f369f3a6ef2c254aefaf5f2b5966f5e135",
    "8ecbce78d6e979cabc184797fdb0aeb33fbef392f560cd11af436b28c1110139",
    "48fd1a31115e118ece5526b6ae91dd2a79707b9c1e3cff9a9745e85e1094321b",
    "ca109e8403bbd28b503bf94d7779b4ee3784394fe90f9fae36f5155e8c4654db",
    "899f8eb24acc508d4ce7a7641f645510c070a99d333e474e030d1f7fa1b9e809",
    "6574d25175bb47c199d1f0b8515bc37b5d3b18e72e6d34cd2ca74bb33edc2153",
    "386136d1870aa74f7909fc22d4a48ca4d6a031f1c5279b59a0edc20d5ec3a9f1",
    "cb4853c17c2e29ec5fe976f5f70a6f07d7a8cd29a3e38d2920bfc6905d58ccf9"
])


def fingerprint(route):
    """Stable route identity includes start mint and every ordered pool direction."""
    if not isinstance(route,dict) or not isinstance(route.get("start_mint"),str):
        raise ValueError("historical route hint requires a valid start")
    legs=route.get("legs")
    if not isinstance(legs,list) or len(legs)!=3:
        raise ValueError("historical route hint requires three source legs")
    selected=[]
    for leg in legs:
        if not isinstance(leg,dict) or any(
                not isinstance(leg.get(key),str) or not leg[key]
                for key in ("venue","pool","input","output")):
            raise ValueError("malformed historical route identity")
        selected.append({key:leg[key] for key in ("venue","pool","input","output")})
    data={"start_mint":route["start_mint"],"legs":selected}
    return hashlib.sha256(json.dumps(
        data,sort_keys=True,separators=(",",":")).encode()).hexdigest()
