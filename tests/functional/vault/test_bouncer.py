import pytest
import brownie 
import json
from brownie import ZERO_ADDRESS, chain, web3, accounts

with open('merkle/merkle_guestlist_test.json') as f:
    testDistribution = json.load(f)

@pytest.fixture
def vault(gov, token, Vault):
    # NOTE: Overriding the one in conftest because it has values already
    vault = gov.deploy(Vault)
    vault.initialize(
        token, gov, gov, "", "", gov
    )
    vault.setDepositLimit(2 ** 256 - 1, {"from": gov})
    yield vault


def test_bouncer_permissions(gov, rando, badgerBouncer, vault):
    # Check that gov is owner (deployer of badgerBouncer):
    assert gov.address == badgerBouncer.owner()

    # Only owner can set guests
    with brownie.reverts():
        badgerBouncer.setVaultGuests(vault.address, [rando.address], [True], {"from": rando})

    badgerBouncer.setVaultGuests(vault.address, [rando.address], [True], {"from": gov})
    assert badgerBouncer.vaultGuests(vault.address, rando.address) == True

    # Only owner can set default guestRoot
    with brownie.reverts():
        badgerBouncer.setDefaultGuestListRoot(
            "0x1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a", 
            {"from": rando}
        )

    badgerBouncer.setDefaultGuestListRoot(
        "0x1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a", 
        {"from": gov}
    )
    assert badgerBouncer.defaultGuestListRoot() == "0x1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a"


    # Only owner can set vault's guestRoot
    with brownie.reverts():
        badgerBouncer.setRootForVault(
            vault.address,
            "0x1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a", 
            {"from": rando}
        )

    badgerBouncer.setRootForVault(
        vault.address,
        "0x1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a", 
        {"from": gov}
    )
    assert badgerBouncer.guestListRootOverride(vault.address) == "0x1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a"
    assert badgerBouncer.removedGuestList(vault.address) == False

    # Only owner can remove vault's guestRoot
    with brownie.reverts():
        badgerBouncer.removeRootForVault(vault.address, {"from": rando})

    badgerBouncer.removeRootForVault(vault.address, {"from": gov})

    assert badgerBouncer.guestListRootOverride(vault.address) == "0x0"
    assert badgerBouncer.removedGuestList(vault.address) == True

    # Only owner can ban an address
    with brownie.reverts():
        badgerBouncer.banAddress(rando.address, {"from": rando})

    badgerBouncer.banAddress(rando.address, {"from": gov})

    assert badgerBouncer.isBanned(rando.address) == True

    # Only owner can unban an address
    with brownie.reverts():
        badgerBouncer.unbanAddress(rando.address, {"from": rando})

    badgerBouncer.unbanAddress(rando.address, {"from": gov})

    assert badgerBouncer.isBanned(rando.address) == False

    # Only owner can set userDepositCap
    with brownie.reverts():
        badgerBouncer.setUserDepositCap(vault.address, 1e18, {"from": rando})

    badgerBouncer.setUserDepositCap(vault.address, 1e18, {"from": gov})
    assert badgerBouncer.userCaps(vault.address) == 1e18

    # Only owner can set totalDepositCap
    with brownie.reverts():
        badgerBouncer.setTotalDepositCap(vault.address, 100e18, {"from": rando})

    badgerBouncer.setTotalDepositCap(vault.address, 100e18, {"from": gov})
    assert badgerBouncer.totalCaps(vault.address) == 100e18

    # Transfer ownership
    badgerBouncer.transferOwnership(rando.address, {"from": gov})
    assert rando.address == badgerBouncer.owner()

    # New owner can perform owner tasks
    badgerBouncer.setTotalDepositCap(vault.address, 0, {"from": rando})



def test_manual_bouncer_flow(gov, rando, vault, token, badgerBouncer):
    # Approve access of badgerBouncer to vault
    vault.approveContractAccess(badgerBouncer.address, {"from": gov})

    # User can deposit while badgerBouncer == Address Zero
    balance = token.balanceOf(gov)
    token.transfer(rando.address, balance, {"from": gov})
    token.approve(badgerBouncer.address, balance * 100, {"from": rando})

    chain.sleep(10)
    chain.mine()

    # Set userDepositCap
    badgerBouncer.setUserDepositCap(vault.address, balance, {"from": gov})
    assert badgerBouncer.userCaps(vault.address) == balance

    # Set totalDepositCap
    badgerBouncer.setTotalDepositCap(vault.address, 2 ** 256 - 1, {"from": gov})
    assert badgerBouncer.totalCaps(vault.address) == 2 ** 256 - 1

    chain.sleep(10)
    chain.mine()

    # User, not in guestlist, can deposit since guestRoot == 0x0 and default guestRoot == 0x0
    assert badgerBouncer.vaultGuests(vault.address, rando.address) == False
    badgerBouncer.deposit(vault.address, balance // 4, {"from": rando})

    assert token.balanceOf(vault) == balance // 4
    assert vault.pricePerShare() == 10 ** token.decimals()  # 1:1 price
    assert vault.balanceOf(rando.address) == balance // 4

    chain.sleep(10)
    chain.mine()

    # Set default guestRoot
    badgerBouncer.setDefaultGuestListRoot(
        "0xc8eb7b9a26b0681320a4f6db1c93891f573fa496b6a99653f11cba4616899027", 
        {"from": gov}
    )
    assert badgerBouncer.defaultGuestListRoot() == "0xc8eb7b9a26b0681320a4f6db1c93891f573fa496b6a99653f11cba4616899027"

    # User, not in guestlist, can't deposit since defaultGuestRoot is set
    assert badgerBouncer.vaultGuests(vault.address, rando.address) == False
    with brownie.reverts():
        badgerBouncer.deposit(vault.address, balance // 4, {"from": rando})

    # Set default guestRoot to 0x0
    badgerBouncer.setDefaultGuestListRoot("0x0", {"from": gov})

    # Set vault's guestRoot
    badgerBouncer.setRootForVault(
        vault.address,
        "0xc8eb7b9a26b0681320a4f6db1c93891f573fa496b6a99653f11cba4616899027", 
        {"from": gov}
    )
    assert badgerBouncer.guestListRootOverride(vault.address) == "0xc8eb7b9a26b0681320a4f6db1c93891f573fa496b6a99653f11cba4616899027"

    # Even if guestRoot is set to 0x0 user, not in guestlist, can't deposit since vault guestRoot is set
    assert badgerBouncer.vaultGuests(vault.address, rando.address) == False
    with brownie.reverts():
        badgerBouncer.deposit(vault.address, balance // 4, {"from": rando})

    # User, not in guestlist, can withdraw
    vault.withdraw(balance // 4, {"from": rando})
    assert vault.balanceOf(rando.address) == 0
    assert token.balanceOf(rando.address) == balance

    chain.sleep(10)
    chain.mine()

    # User is added to badgerBouncer manually
    badgerBouncer.setVaultGuests(vault.address, [rando.address], [True], {"from": gov})
    assert badgerBouncer.vaultGuests(vault.address, rando.address) == True

    chain.sleep(10)
    chain.mine()

    # User, manually added to the badgerBouncer, can deposit
    badgerBouncer.deposit(vault.address, balance // 4, {"from": rando})

    assert token.balanceOf(vault) == balance // 4
    assert vault.pricePerShare() == 10 ** token.decimals()  # 1:1 price
    assert vault.balanceOf(rando.address) == balance // 4

    # User gets banned
    badgerBouncer.banAddress(rando.address, {"from": gov})

    # Banned user can't deposit
    with brownie.reverts():
        badgerBouncer.deposit(vault.address, balance // 4, {"from": rando})

    # User gets unbanned
    badgerBouncer.unbanAddress(rando.address, {"from": gov})

    # Unbanned user can deposit while on the guestlist
    badgerBouncer.deposit(vault.address, balance // 4, {"from": rando})

    assert token.balanceOf(vault) == balance // 2
    assert vault.pricePerShare() == 10 ** token.decimals()  # 1:1 price
    assert vault.balanceOf(rando.address) == balance // 2

    # User is removed from badgerBouncer manually
    badgerBouncer.setVaultGuests(vault.address, [rando.address], [False], {"from": gov})
    assert badgerBouncer.vaultGuests(vault.address, rando.address) == False

    chain.sleep(10)
    chain.mine()

    # User removed from guestlist can't deposit
    with brownie.reverts():
        badgerBouncer.deposit(vault.address, balance // 4, {"from": rando})

    # Remove guestRoot for vault
    badgerBouncer.removeRootForVault(vault.address, {"from": gov})
    assert badgerBouncer.guestListRootOverride(vault.address) == "0x0"
    assert badgerBouncer.removedGuestList(vault.address) == True

    # User, not on guestlist, can deposit since guestRoot for vault is set to 0x0 and 
    # removedGuestList flag is set to True
    badgerBouncer.deposit(vault.address, balance // 2, {"from": rando})

    assert token.balanceOf(vault) == balance
    assert vault.pricePerShare() == 10 ** token.decimals()  # 1:1 price
    assert vault.balanceOf(rando.address) == balance


def test_merkle_bouncer_flow(gov, rando, vault, token, badgerBouncer):
    # Approve access of badgerBouncer to vault
    vault.approveContractAccess(badgerBouncer.address, {"from": gov})

    balance = token.balanceOf(gov)

    # Set guestRoot equal to merkleRoot
    merkleRoot = testDistribution["merkleRoot"]
    badgerBouncer.setRootForVault(vault.address, merkleRoot, {"from": gov})

    with brownie.reverts():
        badgerBouncer.deposit(vault.address, balance // 4, {"from": gov})

    # Test merkle verification upon deposit
    users = [
        web3.toChecksumAddress("0x8107b00171a02f83D7a17f62941841C29c3ae60F"),
        web3.toChecksumAddress("0x716722C80757FFF31DA3F3C392A1736b7cfa3A3e"),
        web3.toChecksumAddress("0xE2e4F2A725E42D0F0EF6291F46c430F963482001"),
    ]

    for user in users:
        user = accounts.at(user, force=True)

        claim = testDistribution["claims"][user]
        proof = claim["proof"]

        # Gov transfers tokens to user
        token.transfer(user.address, balance // 6, {"from": gov})
        token.approve(badgerBouncer, balance * 100, {"from": user})

        badgerBouncer.deposit(vault.address, balance // 10, proof, {"from": user})
        assert vault.balanceOf(user.address) == balance // 10 # Since 1:1 price


    # Test depositing after proveInvitation of a few users
    users = [
        web3.toChecksumAddress("0x1fafb618033Fb07d3a99704a47451971976CB586"),
        web3.toChecksumAddress("0xCf7760E00327f608543c88526427b35049b58984"),
        web3.toChecksumAddress("0xb43b8B43dE2e59A2B44caa2910E31a4E835d4068"),
    ]

    for user in users:
        user = accounts.at(user, force=True)

        claim = testDistribution["claims"][user]
        proof = claim["proof"]

        # Gov transfers tokens to user
        token.transfer(user.address, balance // 6, {"from": gov})
        token.approve(badgerBouncer, balance * 100, {"from": user})

        tx = badgerBouncer.proveInvitation(vault.address, user.address, proof)
        assert tx.events[0]["vault"] == vault.address
        assert tx.events[0]["guestRoot"] == merkleRoot
        assert tx.events[0]["account"] == user.address

        # User deposits 1 token through wrapper (without proof)
        badgerBouncer.deposit(vault.address, balance // 10, {"from": user})
        assert vault.balanceOf(user.address) == balance // 10 # Since 1:1 price



def test_deposit_functions(gov, vault, token, badgerBouncer):
    # Approve access of badgerBouncer to vault
    vault.approveContractAccess(badgerBouncer.address, {"from": gov})

    user = accounts.at("0x8107b00171a02f83D7a17f62941841C29c3ae60F", force = True)
    claim = testDistribution["claims"][user]
    proof = claim["proof"]
    user2 = accounts.at("0xCf7760E00327f608543c88526427b35049b58984", force = True)
    claim2 = testDistribution["claims"][user2]
    proof2 = claim2["proof"]

    balance = token.balanceOf(gov)
    token.transfer(user.address, balance, {"from": gov})
    token.approve(badgerBouncer.address, balance * 100, {"from": user})

    chain.sleep(10)
    chain.mine()

    # Initially, there is no guestlist on vault nor default root so all deposits are allowed
    assert badgerBouncer.defaultGuestListRoot() == "0x0"
    assert badgerBouncer.guestListRootOverride(vault.address) == "0x0"

    # User deposits all without proof
    chain.snapshot() # Take snapshot to revert to
    badgerBouncer.deposit(vault.address, {"from": user})
    assert vault.balanceOf(user.address) == balance # Since 1:1 price
    chain.revert()

    # User deposits an specific amount without proof
    chain.snapshot() # Take snapshot to revert to
    badgerBouncer.deposit(vault.address, balance // 2, {"from": user})
    assert vault.balanceOf(user.address) == balance // 2 # Since 1:1 price
    chain.revert()

    # User deposits an specific amount with proof
    chain.snapshot() # Take snapshot to revert to
    badgerBouncer.setRootForVault(vault.address, testDistribution["merkleRoot"], {"from": gov})
    badgerBouncer.deposit(vault.address, balance // 2, proof, {"from": user})
    assert vault.balanceOf(user.address) == balance // 2 # Since 1:1 price
    chain.revert()

    # User deposits for another user without proof
    chain.snapshot() # Take snapshot to revert to
    badgerBouncer.depositFor(vault.address, user2.address, balance // 2, {"from": user})
    assert vault.balanceOf(user2.address) == balance // 2 # Since 1:1 price
    chain.revert()

    # User deposits for another user with proof
    chain.snapshot() # Take snapshot to revert to
    badgerBouncer.setRootForVault(vault.address, testDistribution["merkleRoot"], {"from": gov})
    badgerBouncer.depositFor(vault.address, user2.address, balance // 2, proof2, {"from": user})
    assert vault.balanceOf(user2.address) == balance // 2 # Since 1:1 price
    chain.revert()


def test_deposit_caps(gov, vault, token, badgerBouncer):
    # Approve access of badgerBouncer to vault
    vault.approveContractAccess(badgerBouncer.address, {"from": gov})

    user = accounts.at("0x8107b00171a02f83D7a17f62941841C29c3ae60F", force = True)
    claim = testDistribution["claims"][user]
    proof = claim["proof"]
    user2 = accounts.at("0xCf7760E00327f608543c88526427b35049b58984", force = True)
    claim2 = testDistribution["claims"][user2]
    proof2 = claim2["proof"]
    user3 = accounts.at("0xb43b8B43dE2e59A2B44caa2910E31a4E835d4068", force = True)
    claim3 = testDistribution["claims"][user3]
    proof3 = claim3["proof"]

    # Transfer balance to users
    balance = token.balanceOf(gov)
    token.transfer(user.address, balance // 3, {"from": gov})
    token.transfer(user2.address, balance // 3, {"from": gov})
    token.transfer(user3.address, balance // 3, {"from": gov})
    token.approve(badgerBouncer.address, balance * 100, {"from": user})
    token.approve(badgerBouncer.address, balance * 100, {"from": user2})
    token.approve(badgerBouncer.address, balance * 100, {"from": user3})

    chain.sleep(10)
    chain.mine()

    # Add guestList to vault
    badgerBouncer.setRootForVault(vault.address, testDistribution["merkleRoot"], {"from": gov})

    # Set userDepositCap
    badgerBouncer.setUserDepositCap(vault.address, balance // 4, {"from": gov})
    assert badgerBouncer.userCaps(vault.address) == balance // 4

    # Set totalDepositCap
    badgerBouncer.setTotalDepositCap(vault.address, balance // 2, {"from": gov})
    assert badgerBouncer.totalCaps(vault.address) == balance // 2

    # == Beginning of Flow == # 
        
    # User attempts to deposit more than allowed by user cap
    with brownie.reverts():
        badgerBouncer.deposit(vault.address, balance // 3, proof, {"from": user})
    
    # Users are able to deposit amounts equal to cap
    badgerBouncer.deposit(vault.address, balance // 4, proof, {"from": user})
    badgerBouncer.deposit(vault.address, balance // 4, proof2, {"from": user2})

    assert vault.balanceOf(user.address) == balance // 4 # Since 1:1 price
    assert vault.balanceOf(user2.address) == balance // 4 # Since 1:1 price
    assert vault.totalSupply() == balance // 2 # Since 1:1 price

    # User attempts to deposit but total cap has been reached
    with brownie.reverts():
        badgerBouncer.deposit(vault.address, balance // 4, proof3, {"from": user3})

    # Remove userDepositCap by setting to 0
    badgerBouncer.setUserDepositCap(vault.address, 0, {"from": gov})
    assert badgerBouncer.userCaps(vault.address) == 0

    # Remove totalDepositCap by setting to MAX
    badgerBouncer.setTotalDepositCap(vault.address, 2 ** 256 - 1, {"from": gov})
    assert badgerBouncer.totalCaps(vault.address) == 2 ** 256 - 1

    # User can now deposit full balance
    badgerBouncer.deposit(vault.address, balance // 3, proof3, {"from": user3})
    assert vault.balanceOf(user3.address) == balance // 3 # Since 1:1 price



def test_multiple_vaults(create_vault, create_token, gov, badgerBouncer):
    # Creation of tokens and vaults
    token1 = create_token()
    vault1 = create_vault(token1, version="1.0.0")
    token2 = create_token()
    vault2 = create_vault(token2, version="1.0.0")
    token3 = create_token()
    vault3 = create_vault(token3, version="1.0.0")

    # Approve access of badgerBouncer to vaults
    vault1.approveContractAccess(badgerBouncer.address, {"from": gov})
    vault2.approveContractAccess(badgerBouncer.address, {"from": gov})
    vault3.approveContractAccess(badgerBouncer.address, {"from": gov})

    user = accounts.at("0x8107b00171a02f83D7a17f62941841C29c3ae60F", force = True)
    claim = testDistribution["claims"][user]
    proof = claim["proof"]

    # Gov transfers tokens to user
    balance1 = token1.balanceOf(gov)
    token1.transfer(user.address, balance1, {"from": gov})
    token1.approve(badgerBouncer.address, balance1 * 100, {"from": user})
    balance2 = token2.balanceOf(gov)
    token2.transfer(user.address, balance2, {"from": gov})
    token2.approve(badgerBouncer.address, balance2 * 100, {"from": user})
    balance3 = token3.balanceOf(gov)
    token3.transfer(user.address, balance3, {"from": gov})
    token3.approve(badgerBouncer.address, balance3 * 100, {"from": user})

    chain.sleep(10)
    chain.mine()

    # User can deposit on three vaults since they don't have guestlist
    badgerBouncer.deposit(vault1.address, balance1 // 4, {"from": user})
    badgerBouncer.deposit(vault2.address, balance2 // 4, {"from": user})
    badgerBouncer.deposit(vault3.address, balance3 // 4, {"from": user})

    chain.sleep(10)
    chain.mine()

    # Guestlist is added as the default
    badgerBouncer.setDefaultGuestListRoot(testDistribution["merkleRoot"], {"from": gov})

    # User can't deposit in any vault without a proof
    with brownie.reverts():
        badgerBouncer.deposit(vault1.address, balance1 // 4, {"from": user})
    with brownie.reverts():
        badgerBouncer.deposit(vault2.address, balance2 // 4, {"from": user})
    with brownie.reverts():
        badgerBouncer.deposit(vault3.address, balance3 // 4, {"from": user})

    # User can deposit with a proof
    badgerBouncer.deposit(vault1.address, balance1 // 4, proof, {"from": user})
    badgerBouncer.deposit(vault2.address, balance2 // 4, proof, {"from": user})
    badgerBouncer.deposit(vault3.address, balance3 // 4, proof, {"from": user})

    chain.sleep(10)
    chain.mine()

    # Default guestlist is removed
    badgerBouncer.setDefaultGuestListRoot("0x0", {"from": gov})

    # Guestlist is added for vault1
    badgerBouncer.setRootForVault(vault1.address, testDistribution["merkleRoot"], {"from": gov})

    # User can't deposit in vault1 without a proof but can on the rest
    with brownie.reverts():
        badgerBouncer.deposit(vault1.address, balance1 // 4, {"from": user})

    badgerBouncer.deposit(vault2.address, balance2 // 4, {"from": user})
    badgerBouncer.deposit(vault3.address, balance3 // 4, {"from": user})

    chain.sleep(10)
    chain.mine()
 
    # User is added to vault1's guestlist manually
    badgerBouncer.setVaultGuests(vault1.address, [user.address], [True], {"from": gov})
    assert badgerBouncer.vaultGuests(vault1.address, user.address) == True

    # Guestlist is added for vault2
    badgerBouncer.setRootForVault(vault2.address, testDistribution["merkleRoot"], {"from": gov})

    # User can't deposit in vault1 with a wrong proof but can on the rest
    with brownie.reverts():
        badgerBouncer.deposit(vault2.address, balance2 // 4, ["0x1a1a"], {"from": user})

    badgerBouncer.deposit(vault1.address, balance1 // 4, {"from": user})
    badgerBouncer.deposit(vault3.address, balance3 // 4, {"from": user})

    chain.sleep(10)
    chain.mine()

    # User is added back to vault2's guestlist manually
    badgerBouncer.setVaultGuests(vault2.address, [user.address], [True], {"from": gov})
    assert badgerBouncer.vaultGuests(vault2.address, user.address) == True

    # User gets completely banned and can't deposit on any vault
    badgerBouncer.banAddress(user.address, {"from": gov})

    with brownie.reverts():
        badgerBouncer.deposit(vault1.address, balance1 // 4, {"from": user})
    with brownie.reverts():
        badgerBouncer.deposit(vault2.address, balance2 // 4, {"from": user})
    with brownie.reverts():
        badgerBouncer.deposit(vault3.address, balance3 // 4, {"from": user})

    # User gets unbanned
    badgerBouncer.unbanAddress(user.address, {"from": gov})

    chain.sleep(10)
    chain.mine()

    # Guestlist is added for vault3 for which user has no proof
    badgerBouncer.setRootForVault(
        vault3.address,
        "0x1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a", 
        {"from": gov}
    )

    # User can't deposit in vault3 (using wrong proof) but can on the rest
    with brownie.reverts():
        badgerBouncer.deposit(vault3.address, balance3 // 4, proof, {"from": user})

    badgerBouncer.deposit(vault1.address, balance1 // 4, {"from": user})
    badgerBouncer.deposit(vault2.address, balance2 // 4, {"from": user})

    assert vault1.balanceOf(user.address) == balance1 # Since 1:1 price
    assert vault2.balanceOf(user.address) == balance2 # Since 1:1 price
    assert vault3.balanceOf(user.address) == balance3 # Since 1:1 price
