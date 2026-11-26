package com.crypticnotes.mobile;

import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import java.nio.charset.StandardCharsets;
import java.security.KeyPairGenerator;
import java.security.KeyStore;
import java.security.PrivateKey;
import java.security.Signature;
import java.security.spec.ECGenParameterSpec;

/**
 * Signs what the plugin sends to the prediction server with a key that lives
 * in this device's Android Keystore: an EC P-256 pair made on first use, whose
 * private half cannot be read out of the device - not by this app either.
 *
 * What the server gets from it: every request is tied to one installation
 * (the public key is its identity, registered the first time it is seen), and
 * a body changed on the way, or made up by something that does not hold the
 * key, fails verification and can be dropped. What it does NOT get: proof
 * that the numbers are true. Someone driving the real app, or registering new
 * installations, signs perfectly well; that is for the server's own limits
 * (one-use match ids, timing, per-key weight) to deal with.
 *
 *   X-Pvp-Key        base64 of the public key, X.509 SubjectPublicKeyInfo (DER)
 *   X-Pvp-Signature  base64 of an ECDSA/SHA-256 signature (DER) over the UTF-8
 *                    bytes of  <path> "\n" <body>,  path being "/predict" or
 *                    "/report" and body exactly the bytes posted
 *
 * Both headers are left out when the device cannot make or use the key; the
 * server then sees an unsigned request and decides what that is worth.
 */
final class PvpSigner {
    private static final String STORE="AndroidKeyStore",ALIAS="pvp_client_key";
    private static String publicKey;

    /** {key, signature} as header values, or null when signing is not possible on this device. */
    static synchronized String[] sign(String path,byte[] body){
        try{
            KeyStore store=KeyStore.getInstance(STORE);store.load(null);
            if(!store.containsAlias(ALIAS)){
                KeyPairGenerator maker=KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC,STORE);
                maker.initialize(new KeyGenParameterSpec.Builder(ALIAS,KeyProperties.PURPOSE_SIGN)
                        .setAlgorithmParameterSpec(new ECGenParameterSpec("secp256r1"))
                        .setDigests(KeyProperties.DIGEST_SHA256).build());
                maker.generateKeyPair();
                publicKey=null;
            }
            if(publicKey==null)publicKey=Base64.encodeToString(store.getCertificate(ALIAS).getPublicKey().getEncoded(),Base64.NO_WRAP);
            Signature signer=Signature.getInstance("SHA256withECDSA");
            signer.initSign((PrivateKey)store.getKey(ALIAS,null));
            signer.update((path+"\n").getBytes(StandardCharsets.UTF_8));signer.update(body);
            return new String[]{publicKey,Base64.encodeToString(signer.sign(),Base64.NO_WRAP)};
        }catch(Exception error){
            android.util.Log.w("CrypticNotes","PVP request not signed",error);
            return null;
        }
    }

    /** Whether this installation already has its key. Never makes one. */
    static synchronized boolean hasKey(){
        try{
            KeyStore store=KeyStore.getInstance(STORE);store.load(null);
            return store.containsAlias(ALIAS);
        }catch(Exception error){
            return false;
        }
    }
    /** As sign(), for requests that are not worth a key of their own (the mailbox): null when there is no key yet. */
    static synchronized String[] signExisting(String path,byte[] body){
        return hasKey()?sign(path,body):null;
    }
}
